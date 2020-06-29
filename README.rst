CZI's Forked Sentry
------------------

Why fork Sentry?
~~~~~~~~~~~~~~~
Well, we run Sentry on our own so it conforms to our PII rules. However,
we also want some features from Sentry's upstream repo that help out our
teams. So, we created this fork! Here we maintain our own releases
of Sentry that will incorporate the cherry picked features we want from
the main branch.

Building a Release:
~~~~~~~~~~~~~~~~~~
We've altered the Makefile a little bit so that it can build a python
wheel for us that we can release in Github.

* Setup:
    * [Install yarn](https://classic.yarnpkg.com/en/docs/install/#mac-stable)
    * [Install nvm](https://github.com/nvm-sh/nvm#installing-and-updating)
    * `nvm install <node_version>` or just `nvm install` to get the latest version of node
* Build:
    * `make publish`

* Release:
    * Executing `make publish` will create a git tag from the latest commit and push it.
    * For now, navigate to the Github UI to create a relase from the latest tag and upload
    the python wheel. You can follow instructions 
    [here](https://help.github.com/en/github/administering-a-repository/managing-releases-in-a-repository)
    

---

What's Sentry?
--------------

Sentry fundamentally is a service that helps you monitor and fix crashes in realtime.
The server is in Python, but it contains a full API for sending events from any
language, in any application.

Official Sentry SDKs
~~~~~~~~~~~~~~~~~~~~
* `JavaScript <https://github.com/getsentry/sentry-javascript>`_
* `React-Native <https://github.com/getsentry/react-native-sentry>`_
* `Python <https://github.com/getsentry/sentry-python>`_
* `Ruby <https://github.com/getsentry/raven-ruby>`_
* `PHP <https://github.com/getsentry/sentry-php>`_
* `Go <https://github.com/getsentry/raven-go>`_
* `Java <https://github.com/getsentry/sentry-java>`_
* `Objective-C/Swift <https://github.com/getsentry/sentry-cocoa>`_
* `C# <https://github.com/getsentry/sentry-dotnet>`_
* `Perl <https://github.com/getsentry/perl-raven>`_
* `Elixir <https://github.com/getsentry/sentry-elixir>`_
* `Laravel <https://github.com/getsentry/sentry-laravel>`_

Resources
---------

* `Documentation <https://docs.sentry.io/>`_
* `Community <https://forum.sentry.io/>`_ (Bugs, feature requests, general questions)
* `Contributing <https://docs.sentry.io/internal/contributing/>`_
* `Bug Tracker <https://github.com/getsentry/sentry/issues>`_
* `Code <https://github.com/getsentry/sentry>`_
* `IRC <irc://irc.freenode.net/sentry>`_  (irc.freenode.net, #sentry)
* `Transifex <https://www.transifex.com/getsentry/sentry/>`_ (Translate Sentry!)
