import datetime
from django.contrib.auth.models import User, AnonymousUser
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from auditlog.middleware import AuditlogMiddleware
from auditlog.models import LogEntry
from testapp.models import SimpleModel, SimpleChildModel, AltPrimaryKeyModel, ProxyModel


class SimpleModelTest(TestCase):
    def setUp(self):
        self.obj = SimpleModel.objects.create(text='I am not difficult.')

    def test_create(self):
        """Creation is logged correctly."""
        # Get the object to work with
        obj = self.obj

        # Check for log entries
        self.assertTrue(obj.history.count() == 1, msg="There is one log entry")

        try:
            history = obj.history.get()
        except obj.history.DoesNotExist:
            self.assertTrue(False, "Log entry exists")
        else:
            self.assertEqual(history.action, LogEntry.Action.CREATE, msg="Action is 'CREATE'")
            self.assertEqual(history.object_repr, str(obj), msg="Representation is equal")

    def test_update(self):
        """Updates are logged correctly."""
        # Get the object to work with
        obj = self.obj

        # Change something
        obj.boolean = True
        obj.save()

        # Check for log entries
        self.assertTrue(obj.history.filter(action=LogEntry.Action.UPDATE).count() == 1, msg="There is one log entry for 'UPDATE'")

        history = obj.history.get(action=LogEntry.Action.UPDATE)

        self.assertJSONEqual(history.changes, '{"boolean": ["False", "True"]}', msg="The change is correctly logged")

    def test_delete(self):
        """Deletion is logged correctly."""
        # Get the object to work with
        obj = self.obj

        history = obj.history.latest()

        # Delete the object
        obj.delete()

        # Check for log entries
        self.assertTrue(LogEntry.objects.filter(content_type=history.content_type, object_pk=history.object_pk, action=LogEntry.Action.DELETE).count() == 1, msg="There is one log entry for 'DELETE'")

    def test_recreate(self):
        SimpleModel.objects.all().delete()
        self.setUp()
        self.test_create()


class SimpleChildModelTest(TestCase):
    def setUp(self):
        self.parent = SimpleModel.objects.create(text='I am your father.')
        self.child = SimpleChildModel.objects.create(parent=self.parent, text='I guess so.')

    def test_create(self):
        """Creation is logged correctly."""
        # Get the objects to work with
        parent = self.parent
        child = self.child

        # Check for log entries
        self.assertTrue(child.history.count() == 1, msg="There is one child log entry")
        self.assertTrue(parent.related_history.count() == 1, msg="There is one parent log entry")

        try:
            history = child.history.get()
        except child.history.DoesNotExist:
            self.assertTrue(False, "Log entry exists")
        else:
            self.assertEqual(history.action, LogEntry.Action.CREATE, msg="Action is 'CREATE'")
            self.assertEqual(history.object_repr, str(child))

        try:
            related = parent.related_history.get()
        except related.related_history.DoesNotExist:
            self.assertTrue(False, "Related history entry exists")
        else:
            self.assertEqual(related.log_entry, history)
            self.assertEqual(related.relation, 'parent')

    def test_update(self):
        """Updates are logged correctly."""
        # Get the objects to work with
        parent = self.parent
        child = self.child

        # Change something
        child.text = "No it isn't true"
        child.save()

        # Check for log entries
        self.assertTrue(child.history.filter(action=LogEntry.Action.UPDATE).count() == 1)

        history = child.history.get(action=LogEntry.Action.UPDATE)

        self.assertJSONEqual(history.changes, '{"text": ["I guess so.", "No it isn\'t true"]}')

        # Check for related entries
        self.assertTrue(parent.related_history.filter(log_entry__action=LogEntry.Action.UPDATE).count() == 1)

    def test_delete(self):
        """Deletion is logged correctly."""
        # Get the object to work with
        parent = self.parent
        child = self.child

        history = child.history.latest()

        # Delete the object
        child.delete()

        # Check for log entries
        self.assertTrue(LogEntry.objects.filter(content_type=history.content_type, object_pk=history.object_pk, action=LogEntry.Action.DELETE).count() == 1)

        # Check for related entries
        self.assertTrue(parent.related_history.filter(log_entry__action=LogEntry.Action.DELETE).count() == 1)

    def test_recreate(self):
        SimpleModel.objects.all().delete()
        self.setUp()
        self.test_create()


class AltPrimaryKeyModelTest(SimpleModelTest):
    def setUp(self):
        self.obj = AltPrimaryKeyModel.objects.create(key=str(datetime.datetime.now()), text='I am strange.')


class ProxyModelTest(SimpleModelTest):
    def setUp(self):
        self.obj = ProxyModel.objects.create(text='I am not what you think.')


class MiddlewareTest(TestCase):
    """
    Test the middleware responsible for connecting and disconnecting the signals used in automatic logging.
    """
    def setUp(self):
        self.middleware = AuditlogMiddleware()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='test', email='test@example.com', password='top_secret')

    def test_request_anonymous(self):
        """No actor will be logged when a user is not logged in."""
        # Create a request
        request = self.factory.get('/')
        request.user = AnonymousUser()

        # Run middleware
        self.middleware.process_request(request)

        # Validate result
        self.assertFalse(pre_save.has_listeners(LogEntry))

        # Finalize transaction
        self.middleware.process_exception(request, None)

    def test_request(self):
        """The actor will be logged when a user is logged in."""
        # Create a request
        request = self.factory.get('/')
        request.user = self.user
        # Run middleware
        self.middleware.process_request(request)

        # Validate result
        self.assertTrue(pre_save.has_listeners(LogEntry))

        # Finalize transaction
        self.middleware.process_exception(request, None)

    def test_response(self):
        """The signal will be disconnected when the request is processed."""
        # Create a request
        request = self.factory.get('/')
        request.user = self.user

        # Run middleware
        self.middleware.process_request(request)
        self.assertTrue(pre_save.has_listeners(LogEntry))  # The signal should be present before trying to disconnect it.
        self.middleware.process_response(request, HttpResponse())

        # Validate result
        self.assertFalse(pre_save.has_listeners(LogEntry))

    def test_exception(self):
        """The signal will be disconnected when an exception is raised."""
        # Create a request
        request = self.factory.get('/')
        request.user = self.user

        # Run middleware
        self.middleware.process_request(request)
        self.assertTrue(pre_save.has_listeners(LogEntry))  # The signal should be present before trying to disconnect it.
        self.middleware.process_exception(request, ValidationError("Test"))

        # Validate result
        self.assertFalse(pre_save.has_listeners(LogEntry))
