// Generated by CoffeeScript 1.3.3
(function() {
  var app,
    __hasProp = {}.hasOwnProperty,
    __extends = function(child, parent) { for (var key in parent) { if (__hasProp.call(parent, key)) child[key] = parent[key]; } function ctor() { this.constructor = child; } ctor.prototype = parent.prototype; child.prototype = new ctor(); child.__super__ = parent.prototype; return child; };

  window.app = app = app || {};

  app.config = app.config || {};

  jQuery(function() {
    var StreamView;
    return app.StreamView = StreamView = (function(_super) {

      __extends(StreamView, _super);

      function StreamView() {
        return StreamView.__super__.constructor.apply(this, arguments);
      }

      StreamView.prototype.el = $('body');

      StreamView.prototype.initialize = function(data) {
        var group_list;
        return group_list = new app.GroupListView({
          id: 'event_list',
          members: data.groups
        });
      };

      return StreamView;

    })(Backbone.View);
  });

  window.app = app = app || {};

  jQuery(function() {
    var GroupList;
    return app.GroupList = GroupList = (function(_super) {

      __extends(GroupList, _super);

      function GroupList() {
        return GroupList.__super__.constructor.apply(this, arguments);
      }

      GroupList.prototype.model = app.Group;

      return GroupList;

    })(Backbone.Collection);
  });

  window.app = app = app || {};

  jQuery(function() {
    var Group, Project, User;
    app.User = User = (function(_super) {

      __extends(User, _super);

      function User() {
        return User.__super__.constructor.apply(this, arguments);
      }

      User.prototype.defaults = {
        name: null,
        avatar: null
      };

      User.prototype.isAnonymous = function() {
        return !(this.id != null);
      };

      User.prototype.isUser = function(user) {
        return this.id === user.id;
      };

      return User;

    })(Backbone.Model);
    app.Project = Project = (function(_super) {

      __extends(Project, _super);

      function Project() {
        return Project.__super__.constructor.apply(this, arguments);
      }

      Project.prototype.defaults = {
        name: null,
        slug: null
      };

      return Project;

    })(Backbone.Model);
    return app.Group = Group = (function(_super) {

      __extends(Group, _super);

      function Group() {
        return Group.__super__.constructor.apply(this, arguments);
      }

      Group.prototype.defaults = {
        tags: [],
        versions: [],
        isBookmarked: false,
        historicalData: []
      };

      Group.prototype.getHistorical = function() {
        if (this.historicalData) {
          return this.historicalData.join(', ');
        } else {
          return '';
        }
      };

      return Group;

    })(Backbone.Model);
  });

  window.app = app = app || {};

  jQuery(function() {
    var GroupListView, GroupView;
    app.GroupListView = GroupListView = (function(_super) {

      __extends(GroupListView, _super);

      function GroupListView() {
        return GroupListView.__super__.constructor.apply(this, arguments);
      }

      GroupListView.prototype.el = '.group-list';

      GroupListView.prototype.model = app.Group;

      GroupListView.prototype.initialize = function(data) {
        var inst, obj, _i, _len, _ref, _results;
        _.bindAll(this);
        this.collection = new app.GroupList;
        this.collection.on('add', this.appendMember);
        this.collection.on('remove', this.clearMember);
        _ref = data.members;
        _results = [];
        for (_i = 0, _len = _ref.length; _i < _len; _i++) {
          obj = _ref[_i];
          inst = new this.model(obj);
          _results.push(this.addMember(inst));
        }
        return _results;
      };

      GroupListView.prototype.changed = function() {
        return this.trigger("membership");
      };

      GroupListView.prototype.addMember = function(obj) {
        if (!this.hasMember(obj)) {
          return this.collection.add(obj);
        } else {
          obj = this.collection.get(obj.id);
          return obj.set('count', obj.get("count"));
        }
      };

      GroupListView.prototype.hasMember = function(obj) {
        if (this.collection.get(obj.id)) {
          return true;
        } else {
          return false;
        }
      };

      GroupListView.prototype.removeMember = function(obj) {
        return this.collection.remove(obj);
      };

      GroupListView.prototype.appendMember = function(obj) {
        var out, view;
        view = new GroupView({
          model: obj,
          id: this.id + obj.id
        });
        out = view.render();
        return $('#' + this.id).append(out.el);
      };

      GroupListView.prototype.clearMember = function(obj) {
        return $('li[data-id="' + this.id + '"]', el).remove();
      };

      return GroupListView;

    })(Backbone.View);
    return app.GroupView = GroupView = (function(_super) {

      __extends(GroupView, _super);

      function GroupView() {
        return GroupView.__super__.constructor.apply(this, arguments);
      }

      GroupView.prototype.tagName = 'li';

      GroupView.prototype.className = 'group';

      GroupView.prototype.template = _.template($('#group-template').html());

      GroupView.prototype.initialize = function() {
        _.bindAll(this);
        return this.model.on("change:count", this.updateCount);
      };

      GroupView.prototype.render = function() {
        this.$el.html(this.template({
          model: this.model
        }));
        return this;
      };

      GroupView.prototype.updateCount = function(obj) {
        return $('.count span', this.$el).text(this.model.get("count"));
      };

      return GroupView;

    })(Backbone.View);
  });

}).call(this);
