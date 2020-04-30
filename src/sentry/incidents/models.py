from __future__ import absolute_import

from collections import namedtuple

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, models, transaction
from django.db.models.signals import post_delete, post_save
from django.utils import timezone
from enum import Enum

from sentry.db.models import FlexibleForeignKey, Model, UUIDField, OneToOneCascadeDeletes
from sentry.db.models import ArrayField, sane_repr
from sentry.db.models.manager import BaseManager
from sentry.models import Team, User
from sentry.snuba.models import QueryAggregations, QuerySubscription
from sentry.utils import metrics
from sentry.utils.retries import TimedRetryPolicy


class IncidentProject(Model):
    __core__ = False

    project = FlexibleForeignKey("sentry.Project", db_index=False, db_constraint=False)
    incident = FlexibleForeignKey("sentry.Incident")

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentproject"
        unique_together = (("project", "incident"),)


class IncidentGroup(Model):
    __core__ = False

    group = FlexibleForeignKey("sentry.Group", db_index=False, db_constraint=False)
    incident = FlexibleForeignKey("sentry.Incident")

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentgroup"
        unique_together = (("group", "incident"),)


class IncidentSeen(Model):
    __core__ = False

    incident = FlexibleForeignKey("sentry.Incident")
    user = FlexibleForeignKey(settings.AUTH_USER_MODEL, db_index=False)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentseen"
        unique_together = (("user", "incident"),)


class IncidentManager(BaseManager):
    CACHE_KEY = "incidents:active:%s:%s"

    def fetch_for_organization(self, organization, projects):
        return self.filter(organization=organization, projects__in=projects).distinct()

    @classmethod
    def _build_active_incident_cache_key(self, alert_rule_id, project_id):
        return self.CACHE_KEY % (alert_rule_id, project_id)

    def get_active_incident(self, alert_rule, project):
        cache_key = self._build_active_incident_cache_key(alert_rule.id, project.id)
        incident = cache.get(cache_key)
        if incident is None:
            try:
                incident = (
                    Incident.objects.filter(
                        type=IncidentType.ALERT_TRIGGERED.value,
                        alert_rule=alert_rule,
                        projects=project,
                    )
                    .exclude(status=IncidentStatus.CLOSED.value)
                    .order_by("-date_added")[0]
                )
            except IndexError:
                # Set this to False so that we can have a negative cache as well.
                incident = False
            cache.set(cache_key, incident)
            if incident is False:
                incident = None
        elif not incident:
            # If we had a falsey not None value in the cache, then we stored that there
            # are no current active incidents. Just set to None
            incident = None

        return incident

    @classmethod
    def clear_active_incident_cache(cls, instance, **kwargs):
        for project in instance.projects.all():
            cache.delete(cls._build_active_incident_cache_key(instance.alert_rule_id, project.id))

    @classmethod
    def clear_active_incident_project_cache(cls, instance, **kwargs):
        cache.delete(
            cls._build_active_incident_cache_key(
                instance.incident.alert_rule_id, instance.project_id
            )
        )

    @TimedRetryPolicy.wrap(timeout=5, exceptions=(IntegrityError,))
    def create(self, organization, **kwargs):
        """
        Creates an Incident. Fetches the maximum identifier value for the org
        and increments it by one. If two incidents are created for the
        Organization at the same time then an integrity error will be thrown,
        and we'll retry again several times. I prefer to lock optimistically
        here since if we're creating multiple Incidents a second for an
        Organization then we're likely failing at making Incidents useful.
        """
        with transaction.atomic():
            result = self.filter(organization=organization).aggregate(models.Max("identifier"))
            identifier = result["identifier__max"]
            if identifier is None:
                identifier = 1
            else:
                identifier += 1

            return super(IncidentManager, self).create(
                organization=organization, identifier=identifier, **kwargs
            )


class IncidentType(Enum):
    DETECTED = 0
    ALERT_TRIGGERED = 2


class IncidentStatus(Enum):
    OPEN = 1
    CLOSED = 2
    WARNING = 10
    CRITICAL = 20


class IncidentStatusMethod(Enum):
    MANUAL = 1
    RULE_UPDATED = 2
    RULE_TRIGGERED = 3


INCIDENT_STATUS = {
    IncidentStatus.OPEN: "Open",
    IncidentStatus.CLOSED: "Resolved",
    IncidentStatus.CRITICAL: "Critical",
    IncidentStatus.WARNING: "Warning",
}


class Incident(Model):
    __core__ = True

    objects = IncidentManager()

    organization = FlexibleForeignKey("sentry.Organization")
    projects = models.ManyToManyField(
        "sentry.Project", related_name="incidents", through=IncidentProject
    )
    groups = models.ManyToManyField("sentry.Group", related_name="incidents", through=IncidentGroup)
    alert_rule = FlexibleForeignKey("sentry.AlertRule", null=True, on_delete=models.SET_NULL)
    # Incrementing id that is specific to the org.
    identifier = models.IntegerField()
    # Identifier used to match incoming events from the detection algorithm
    detection_uuid = UUIDField(null=True, db_index=True)
    status = models.PositiveSmallIntegerField(default=IncidentStatus.OPEN.value)
    status_method = models.PositiveSmallIntegerField(
        default=IncidentStatusMethod.RULE_TRIGGERED.value
    )
    type = models.PositiveSmallIntegerField()
    aggregation = models.PositiveSmallIntegerField(default=QueryAggregations.TOTAL.value)
    title = models.TextField()
    # Query used to fetch events related to an incident
    query = models.TextField()
    # When we suspect the incident actually started
    date_started = models.DateTimeField(default=timezone.now)
    # When we actually detected the incident
    date_detected = models.DateTimeField(default=timezone.now)
    date_added = models.DateTimeField(default=timezone.now)
    date_closed = models.DateTimeField(null=True)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incident"
        unique_together = (("organization", "identifier"),)
        index_together = (("alert_rule", "type", "status"),)

    @property
    def current_end_date(self):
        """
        Returns the current end of the incident. Either the date it was closed,
        or the current time if it's still open.
        """
        return self.date_closed if self.date_closed else timezone.now()

    @property
    def duration(self):
        return self.current_end_date - self.date_started


class PendingIncidentSnapshot(Model):
    __core__ = True

    incident = OneToOneCascadeDeletes("sentry.Incident")
    target_run_date = models.DateTimeField(db_index=True, default=timezone.now)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_pendingincidentsnapshot"


class IncidentSnapshot(Model):
    __core__ = True

    incident = OneToOneCascadeDeletes("sentry.Incident")
    event_stats_snapshot = FlexibleForeignKey("sentry.TimeSeriesSnapshot")
    unique_users = models.IntegerField()
    total_events = models.IntegerField()
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentsnapshot"


class TimeSeriesSnapshot(Model):
    __core__ = True

    start = models.DateTimeField()
    end = models.DateTimeField()
    values = ArrayField(of=ArrayField(models.IntegerField()))
    period = models.IntegerField()
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_timeseriessnapshot"

    @property
    def snuba_values(self):
        """
        Returns values matching the snuba format, a list of dicts with 'time'
        and 'count' keys.
        :return:
        """
        return {"data": [{"time": time, "count": count} for time, count in self.values]}


class IncidentActivityType(Enum):
    DETECTED = 1
    STATUS_CHANGE = 2
    COMMENT = 3


class IncidentActivity(Model):
    __core__ = True

    incident = FlexibleForeignKey("sentry.Incident")
    user = FlexibleForeignKey("sentry.User", null=True)
    type = models.IntegerField()
    value = models.TextField(null=True)
    previous_value = models.TextField(null=True)
    comment = models.TextField(null=True)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentactivity"


class IncidentSubscription(Model):
    __core__ = True

    incident = FlexibleForeignKey("sentry.Incident", db_index=False)
    user = FlexibleForeignKey(settings.AUTH_USER_MODEL)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidentsubscription"
        unique_together = (("incident", "user"),)

    __repr__ = sane_repr("incident_id", "user_id")


class AlertRuleStatus(Enum):
    PENDING = 0
    SNAPSHOT = 4


class AlertRuleThresholdType(Enum):
    ABOVE = 0
    BELOW = 1


class AlertRuleManager(BaseManager):
    """
    A manager that excludes all rows that are snapshots.
    """

    CACHE_SUBSCRIPTION_KEY = "alert_rule:subscription:%s"

    def get_queryset(self):
        return (
            super(AlertRuleManager, self)
            .get_queryset()
            .exclude(status=AlertRuleStatus.SNAPSHOT.value)
        )

    def fetch_for_organization(self, organization):
        return self.filter(organization=organization)

    def fetch_for_project(self, project):
        return self.filter(query_subscriptions__project=project)

    @classmethod
    def __build_subscription_cache_key(self, subscription_id):
        return self.CACHE_SUBSCRIPTION_KEY % subscription_id

    def get_for_subscription(self, subscription):
        """
        Fetches the AlertRule associated with a Subscription. Attempts to fetch from
        cache then hits the database
        """
        cache_key = self.__build_subscription_cache_key(subscription.id)
        alert_rule = cache.get(cache_key)
        if alert_rule is None:
            alert_rule = AlertRule.objects.get(query_subscriptions=subscription)
            cache.set(cache_key, alert_rule, 3600)

        return alert_rule

    @classmethod
    def clear_subscription_cache(cls, instance, **kwargs):
        cache.delete(cls.__build_subscription_cache_key(instance.id))

    @classmethod
    def clear_alert_rule_subscription_caches(cls, instance, **kwargs):
        subscription_ids = AlertRuleQuerySubscription.objects.filter(
            alert_rule=instance
        ).values_list("query_subscription_id", flat=True)
        if subscription_ids:
            cache.delete_many(
                cls.__build_subscription_cache_key(sub_id) for sub_id in subscription_ids
            )


class AlertRuleEnvironment(Model):
    __core__ = True

    environment = FlexibleForeignKey("sentry.Environment")
    alert_rule = FlexibleForeignKey("sentry.AlertRule")

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertruleenvironment"
        unique_together = (("alert_rule", "environment"),)


class AlertRuleQuerySubscription(Model):
    __core__ = True

    query_subscription = FlexibleForeignKey("sentry.QuerySubscription", unique=True)
    alert_rule = FlexibleForeignKey("sentry.AlertRule")

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertrulequerysubscription"


class AlertRuleExcludedProjects(Model):
    __core__ = True

    alert_rule = FlexibleForeignKey("sentry.AlertRule", db_index=False)
    project = FlexibleForeignKey("sentry.Project", db_constraint=False)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertruleexcludedprojects"
        unique_together = (("alert_rule", "project"),)


class AlertRule(Model):
    __core__ = True

    objects = AlertRuleManager()
    objects_with_snapshots = BaseManager()

    organization = FlexibleForeignKey("sentry.Organization", null=True)
    query_subscriptions = models.ManyToManyField(
        "sentry.QuerySubscription", related_name="alert_rules", through=AlertRuleQuerySubscription
    )
    excluded_projects = models.ManyToManyField(
        "sentry.Project", related_name="alert_rule_exclusions", through=AlertRuleExcludedProjects
    )
    name = models.TextField()
    status = models.SmallIntegerField(default=AlertRuleStatus.PENDING.value)
    dataset = models.TextField()
    query = models.TextField()
    environment = models.ManyToManyField(
        "sentry.Environment", related_name="alert_rule_environment", through=AlertRuleEnvironment
    )
    # Determines whether we include all current and future projects from this
    # organization in this rule.
    include_all_projects = models.BooleanField(default=False)
    # TODO: Remove this default after we migrate
    aggregation = models.IntegerField(default=QueryAggregations.TOTAL.value)
    time_window = models.IntegerField()
    resolution = models.IntegerField()
    threshold_period = models.IntegerField()
    date_modified = models.DateTimeField(default=timezone.now)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertrule"
        base_manager_name = "objects_with_snapshots"
        default_manager_name = "objects_with_snapshots"
        # This constraint does not match what is in migration 0061, since there is no
        # way to declare an index on an expression. Therefore, tests would break depending
        # on whether we run migrations - to work around this, we skip some tests if
        # migrations have not been run. In migration 0061, this index is set to
        # a partial index where status=0
        unique_together = (("organization", "name", "status"),)

    __repr__ = sane_repr("id", "name", "date_added")


class TriggerStatus(Enum):
    ACTIVE = 0
    RESOLVED = 1


class IncidentTriggerManager(BaseManager):
    CACHE_KEY = "incident:triggers:%s"

    @classmethod
    def _build_cache_key(self, incident_id):
        return self.CACHE_KEY % incident_id

    def get_for_incident(self, incident):
        """
        Fetches the IncidentTriggers associated with an Incident. Attempts to fetch from
        cache then hits the database.
        """
        cache_key = self._build_cache_key(incident.id)
        triggers = cache.get(cache_key)
        if triggers is None:
            triggers = list(IncidentTrigger.objects.filter(incident=incident))
            cache.set(cache_key, triggers, 3600)

        return triggers

    @classmethod
    def clear_incident_cache(cls, instance, **kwargs):
        cache.delete(cls._build_cache_key(instance.id))

    @classmethod
    def clear_incident_trigger_cache(cls, instance, **kwargs):
        cache.delete(cls._build_cache_key(instance.incident_id))


class IncidentTrigger(Model):
    __core__ = True

    objects = IncidentTriggerManager()

    incident = FlexibleForeignKey("sentry.Incident", db_index=False)
    alert_rule_trigger = FlexibleForeignKey("sentry.AlertRuleTrigger")
    status = models.SmallIntegerField()
    date_modified = models.DateTimeField(default=timezone.now, null=False)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_incidenttrigger"
        unique_together = (("incident", "alert_rule_trigger"),)


class AlertRuleTriggerManager(BaseManager):
    CACHE_KEY = "alert_rule_triggers:alert_rule:%s"

    @classmethod
    def _build_trigger_cache_key(self, alert_rule_id):
        return self.CACHE_KEY % alert_rule_id

    def get_for_alert_rule(self, alert_rule):
        """
        Fetches the AlertRuleTriggers associated with an AlertRule. Attempts to fetch
        from cache then hits the database
        """
        cache_key = self._build_trigger_cache_key(alert_rule.id)
        triggers = cache.get(cache_key)
        if triggers is None:
            triggers = list(AlertRuleTrigger.objects.filter(alert_rule=alert_rule))
            cache.set(cache_key, triggers, 3600)
        return triggers

    @classmethod
    def clear_trigger_cache(cls, instance, **kwargs):
        cache.delete(cls._build_trigger_cache_key(instance.alert_rule_id))

    @classmethod
    def clear_alert_rule_trigger_cache(cls, instance, **kwargs):
        cache.delete(cls._build_trigger_cache_key(instance.id))


class AlertRuleTrigger(Model):
    __core__ = True

    alert_rule = FlexibleForeignKey("sentry.AlertRule")
    label = models.TextField()
    threshold_type = models.SmallIntegerField()
    alert_threshold = models.IntegerField()
    resolve_threshold = models.IntegerField(null=True)
    triggered_incidents = models.ManyToManyField(
        "sentry.Incident", related_name="triggers", through=IncidentTrigger
    )
    date_added = models.DateTimeField(default=timezone.now)

    objects = AlertRuleTriggerManager()

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertruletrigger"
        unique_together = (("alert_rule", "label"),)


class AlertRuleTriggerExclusion(Model):
    __core__ = True

    alert_rule_trigger = FlexibleForeignKey("sentry.AlertRuleTrigger", related_name="exclusions")
    query_subscription = FlexibleForeignKey("sentry.QuerySubscription")
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertruletriggerexclusion"
        unique_together = (("alert_rule_trigger", "query_subscription"),)


class AlertRuleTriggerAction(Model):
    """
    This model represents an action that occurs when a trigger is fired. This is
    typically some sort of notification.
    """

    __core__ = True

    _type_registrations = {}

    # Which sort of action to take
    class Type(Enum):
        EMAIL = 0
        PAGERDUTY = 1
        SLACK = 2

    class TargetType(Enum):
        # A direct reference, like an email address, Slack channel or PagerDuty service
        SPECIFIC = 0
        # A specific user. This could be used to grab the user's email address.
        USER = 1
        # A specific team. This could be used to send an email to everyone associated
        # with a team.
        TEAM = 2

    TypeRegistration = namedtuple(
        "TypeRegistration",
        ["handler", "slug", "type", "supported_target_types", "integration_provider"],
    )

    alert_rule_trigger = FlexibleForeignKey("sentry.AlertRuleTrigger")
    integration = FlexibleForeignKey("sentry.Integration", null=True)
    type = models.SmallIntegerField()
    target_type = models.SmallIntegerField()
    # Identifier used to perform the action on a given target
    target_identifier = models.TextField(null=True)
    # Human readable name to display in the UI
    target_display = models.TextField(null=True)
    date_added = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_alertruletriggeraction"

    @property
    def target(self):
        if self.target_type == self.TargetType.USER.value:
            try:
                return User.objects.get(id=int(self.target_identifier))
            except User.DoesNotExist:
                pass
        elif self.target_type == self.TargetType.TEAM.value:
            try:
                return Team.objects.get(id=int(self.target_identifier))
            except Team.DoesNotExist:
                pass
        elif self.target_type == self.TargetType.SPECIFIC.value:
            # TODO: This is only for email. We should have a way of validating that it's
            # ok to contact this email.
            return self.target_identifier

    def build_handler(self, incident, project):
        type = AlertRuleTriggerAction.Type(self.type)
        if type in self._type_registrations:
            return self._type_registrations[type].handler(self, incident, project)
        else:
            metrics.incr("alert_rule_trigger.unhandled_type.{}".format(self.type))

    def fire(self, incident, project):
        handler = self.build_handler(incident, project)
        if handler:
            return handler.fire()

    def resolve(self, incident, project):
        handler = self.build_handler(incident, project)
        if handler:
            return handler.resolve()

    @classmethod
    def register_type(cls, slug, type, supported_target_types, integration_provider=None):
        """
        Registers a handler for a given type.
        :param slug: A string representing the name of this type registration
        :param type: The `Type` to handle.
        :param handler: A subclass of `ActionHandler` that accepts the
        `AlertRuleTriggerAction` and `Incident`.
        :param integration_provider: String representing the integration provider
        related to this type.
        """

        def inner(handler):
            if type not in cls._type_registrations:
                cls._type_registrations[type] = cls.TypeRegistration(
                    handler, slug, type, frozenset(supported_target_types), integration_provider
                )
            else:
                raise Exception(u"Handler already registered for type %s" % type)
            return handler

        return inner

    @classmethod
    def get_registered_type(cls, type):
        return cls._type_registrations[type]

    @classmethod
    def get_registered_types(cls):
        return cls._type_registrations.values()


post_delete.connect(AlertRuleManager.clear_subscription_cache, sender=QuerySubscription)
post_save.connect(AlertRuleManager.clear_subscription_cache, sender=QuerySubscription)
post_save.connect(AlertRuleManager.clear_alert_rule_subscription_caches, sender=AlertRule)
post_delete.connect(AlertRuleManager.clear_alert_rule_subscription_caches, sender=AlertRule)

post_delete.connect(AlertRuleTriggerManager.clear_alert_rule_trigger_cache, sender=AlertRule)
post_save.connect(AlertRuleTriggerManager.clear_alert_rule_trigger_cache, sender=AlertRule)
post_save.connect(AlertRuleTriggerManager.clear_trigger_cache, sender=AlertRuleTrigger)
post_delete.connect(AlertRuleTriggerManager.clear_trigger_cache, sender=AlertRuleTrigger)

post_save.connect(IncidentManager.clear_active_incident_cache, sender=Incident)
post_save.connect(IncidentManager.clear_active_incident_project_cache, sender=IncidentProject)
post_delete.connect(IncidentManager.clear_active_incident_project_cache, sender=IncidentProject)

post_delete.connect(IncidentTriggerManager.clear_incident_cache, sender=Incident)
post_save.connect(IncidentTriggerManager.clear_incident_trigger_cache, sender=IncidentTrigger)
post_delete.connect(IncidentTriggerManager.clear_incident_trigger_cache, sender=IncidentTrigger)
