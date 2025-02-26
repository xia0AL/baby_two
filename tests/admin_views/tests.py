# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import os
import re
import unittest

from django.contrib.admin import ModelAdmin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.admin.options import TO_FIELD_VAR
from django.contrib.admin.templatetags.admin_static import static
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.tests import AdminSeleniumWebDriverTestCase
from django.contrib.admin.utils import quote
from django.contrib.admin.validation import ModelAdminValidator
from django.contrib.admin.views.main import IS_POPUP_VAR
# Register auth models with the admin.
from django.contrib.auth import REDIRECT_FIELD_NAME, get_permission_codename
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core import mail
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from django.core.files import temp as tempfile
from django.core.urlresolvers import (
    NoReverseMatch, get_script_prefix, reverse, set_script_prefix,
)
from django.forms.utils import ErrorList
from django.template.response import TemplateResponse
from django.test import (
    TestCase, modify_settings, override_settings, skipUnlessDBFeature,
)
from django.test.utils import patch_logger
from django.utils import formats, six, translation
from django.utils._os import upath
from django.utils.cache import get_max_age
from django.utils.encoding import force_bytes, force_text, iri_to_uri
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.six.moves.urllib.parse import parse_qsl, urljoin, urlparse

from .admin import CityAdmin, site, site2
from .models import (
    Actor, AdminOrderedAdminMethod, AdminOrderedCallable, AdminOrderedField,
    AdminOrderedModelMethod, Answer, Article, BarAccount, Book, Category,
    Chapter, Character, Child, Choice, City, Collector, Color2,
    ComplexSortedPerson, CoverLetter, CustomArticle, DooHickey, Employee,
    EmptyModel, FancyDoodad, FieldOverridePost, FilteredManager, FooAccount,
    FoodDelivery, FunkyTag, Gallery, Grommet, Inquisition, Language,
    MainPrepopulated, ModelWithStringPrimaryKey, OtherStory, Paper, Parent,
    ParentWithDependentChildren, Person, Persona, Picture, Pizza, Plot,
    PluggableSearchPerson, Podcast, Post, Promo, Question, RelatedPrepopulated,
    Report, Restaurant, RowLevelChangePermissionModel, Section, ShortMessage,
    Simple, Story, Subscriber, Telegram, Topping, UnchangeableObject,
    UndeletableObject, UnorderedObject, Vodcast, Whatsit, Widget, Worker,
    WorkHour,
)


ERROR_MESSAGE = "Please enter the correct username and password \
for a staff account. Note that both fields may be case-sensitive."


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
                   ROOT_URLCONF="admin_views.urls",
                   USE_I18N=True, USE_L10N=False, LANGUAGE_CODE='en')
class AdminViewBasicTestCase(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-colors.xml',
                'admin-views-fabrics.xml', 'admin-views-books.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def tearDown(self):
        formats.reset_format_cache()

    def assertContentBefore(self, response, text1, text2, failing_msg=None):
        """
        Testing utility asserting that text1 appears before text2 in response
        content.
        """
        self.assertEqual(response.status_code, 200)
        self.assertLess(response.content.index(force_bytes(text1)), response.content.index(force_bytes(text2)),
            failing_msg)


class AdminViewBasicTest(AdminViewBasicTestCase):
    def test_trailing_slash_required(self):
        """
        If you leave off the trailing slash, app should redirect and add it.
        """
        add_url = reverse('admin:admin_views_article_add')
        response = self.client.get(add_url[:-1])
        self.assertRedirects(response, add_url, status_code=301)

    def test_admin_static_template_tag(self):
        """
        Test that admin_static.static is pointing to the collectstatic version
        (as django.contrib.collectstatic is in installed apps).
        """
        old_url = staticfiles_storage.base_url
        staticfiles_storage.base_url = '/test/'
        try:
            self.assertEqual(static('path'), '/test/path')
        finally:
            staticfiles_storage.base_url = old_url

    def test_basic_add_GET(self):
        """
        A smoke test to ensure GET on the add_view works.
        """
        response = self.client.get(reverse('admin:admin_views_section_add'))
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.status_code, 200)

    def test_add_with_GET_args(self):
        response = self.client.get(reverse('admin:admin_views_section_add'), {'name': 'My Section'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="My Section"',
            msg_prefix="Couldn't find an input with the right value in the response")

    def test_basic_edit_GET(self):
        """
        A smoke test to ensure GET on the change_view works.
        """
        response = self.client.get(reverse('admin:admin_views_section_change', args=(1,)))
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.status_code, 200)

    def test_basic_edit_GET_string_PK(self):
        """
        Ensure GET on the change_view works (returns an HTTP 404 error, see
        #11191) when passing a string as the PK argument for a model with an
        integer PK field.
        """
        response = self.client.get(reverse('admin:admin_views_section_change', args=('abc',)))
        self.assertEqual(response.status_code, 404)

    def test_basic_inheritance_GET_string_PK(self):
        """
        Ensure GET on the change_view works on inherited models (returns an
        HTTP 404 error, see #19951) when passing a string as the PK argument
        for a model with an integer PK field.
        """
        response = self.client.get(reverse('admin:admin_views_supervillain_change', args=('abc',)))
        self.assertEqual(response.status_code, 404)

    def test_basic_add_POST(self):
        """
        A smoke test to ensure POST on add_view works.
        """
        post_data = {
            "name": "Another Section",
            # inline data
            "article_set-TOTAL_FORMS": "3",
            "article_set-INITIAL_FORMS": "0",
            "article_set-MAX_NUM_FORMS": "0",
        }
        response = self.client.post(reverse('admin:admin_views_section_add'), post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere

    def test_popup_add_POST(self):
        """
        Ensure http response from a popup is properly escaped.
        """
        post_data = {
            '_popup': '1',
            'title': 'title with a new\nline',
            'content': 'some content',
            'date_0': '2010-09-10',
            'date_1': '14:55:39',
        }
        response = self.client.post(reverse('admin:admin_views_article_add'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dismissAddRelatedObjectPopup')
        self.assertContains(response, 'title with a new\\u000Aline')

    # Post data for edit inline
    inline_post_data = {
        "name": "Test section",
        # inline data
        "article_set-TOTAL_FORMS": "6",
        "article_set-INITIAL_FORMS": "3",
        "article_set-MAX_NUM_FORMS": "0",
        "article_set-0-id": "1",
        # there is no title in database, give one here or formset will fail.
        "article_set-0-title": "Norske bostaver æøå skaper problemer",
        "article_set-0-content": "&lt;p&gt;Middle content&lt;/p&gt;",
        "article_set-0-date_0": "2008-03-18",
        "article_set-0-date_1": "11:54:58",
        "article_set-0-section": "1",
        "article_set-1-id": "2",
        "article_set-1-title": "Need a title.",
        "article_set-1-content": "&lt;p&gt;Oldest content&lt;/p&gt;",
        "article_set-1-date_0": "2000-03-18",
        "article_set-1-date_1": "11:54:58",
        "article_set-2-id": "3",
        "article_set-2-title": "Need a title.",
        "article_set-2-content": "&lt;p&gt;Newest content&lt;/p&gt;",
        "article_set-2-date_0": "2009-03-18",
        "article_set-2-date_1": "11:54:58",
        "article_set-3-id": "",
        "article_set-3-title": "",
        "article_set-3-content": "",
        "article_set-3-date_0": "",
        "article_set-3-date_1": "",
        "article_set-4-id": "",
        "article_set-4-title": "",
        "article_set-4-content": "",
        "article_set-4-date_0": "",
        "article_set-4-date_1": "",
        "article_set-5-id": "",
        "article_set-5-title": "",
        "article_set-5-content": "",
        "article_set-5-date_0": "",
        "article_set-5-date_1": "",
    }

    def test_basic_edit_POST(self):
        """
        A smoke test to ensure POST on edit_view works.
        """
        response = self.client.post(reverse('admin:admin_views_section_change', args=(1,)), self.inline_post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere

    def test_edit_save_as(self):
        """
        Test "save as".
        """
        post_data = self.inline_post_data.copy()
        post_data.update({
            '_saveasnew': 'Save+as+new',
            "article_set-1-section": "1",
            "article_set-2-section": "1",
            "article_set-3-section": "1",
            "article_set-4-section": "1",
            "article_set-5-section": "1",
        })
        response = self.client.post(reverse('admin:admin_views_section_change', args=(1,)), post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere

    def test_edit_save_as_delete_inline(self):
        """
        Should be able to "Save as new" while also deleting an inline.
        """
        post_data = self.inline_post_data.copy()
        post_data.update({
            '_saveasnew': 'Save+as+new',
            "article_set-1-section": "1",
            "article_set-2-section": "1",
            "article_set-2-DELETE": "1",
            "article_set-3-section": "1",
        })
        response = self.client.post(reverse('admin:admin_views_section_change', args=(1,)), post_data)
        self.assertEqual(response.status_code, 302)
        # started with 3 articles, one was deleted.
        self.assertEqual(Section.objects.latest('id').article_set.count(), 2)

    def test_change_list_sorting_callable(self):
        """
        Ensure we can sort on a list_display field that is a callable
        (column 2 is callable_year in ArticleAdmin)
        """
        response = self.client.get(reverse('admin:admin_views_article_changelist'), {'o': 2})
        self.assertContentBefore(response, 'Oldest content', 'Middle content',
            "Results of sorting on callable are out of order.")
        self.assertContentBefore(response, 'Middle content', 'Newest content',
            "Results of sorting on callable are out of order.")

    def test_change_list_sorting_model(self):
        """
        Ensure we can sort on a list_display field that is a Model method
        (column 3 is 'model_year' in ArticleAdmin)
        """
        response = self.client.get(reverse('admin:admin_views_article_changelist'), {'o': '-3'})
        self.assertContentBefore(response, 'Newest content', 'Middle content',
            "Results of sorting on Model method are out of order.")
        self.assertContentBefore(response, 'Middle content', 'Oldest content',
            "Results of sorting on Model method are out of order.")

    def test_change_list_sorting_model_admin(self):
        """
        Ensure we can sort on a list_display field that is a ModelAdmin method
        (column 4 is 'modeladmin_year' in ArticleAdmin)
        """
        response = self.client.get(reverse('admin:admin_views_article_changelist'), {'o': '4'})
        self.assertContentBefore(response, 'Oldest content', 'Middle content',
            "Results of sorting on ModelAdmin method are out of order.")
        self.assertContentBefore(response, 'Middle content', 'Newest content',
            "Results of sorting on ModelAdmin method are out of order.")

    def test_change_list_sorting_model_admin_reverse(self):
        """
        Ensure we can sort on a list_display field that is a ModelAdmin
        method in reverse order (i.e. admin_order_field uses the '-' prefix)
        (column 6 is 'model_year_reverse' in ArticleAdmin)
        """
        response = self.client.get(reverse('admin:admin_views_article_changelist'), {'o': '6'})
        self.assertContentBefore(response, '2009', '2008',
            "Results of sorting on ModelAdmin method are out of order.")
        self.assertContentBefore(response, '2008', '2000',
            "Results of sorting on ModelAdmin method are out of order.")
        # Let's make sure the ordering is right and that we don't get a
        # FieldError when we change to descending order
        response = self.client.get(reverse('admin:admin_views_article_changelist'), {'o': '-6'})
        self.assertContentBefore(response, '2000', '2008',
            "Results of sorting on ModelAdmin method are out of order.")
        self.assertContentBefore(response, '2008', '2009',
            "Results of sorting on ModelAdmin method are out of order.")

    def test_change_list_sorting_multiple(self):
        p1 = Person.objects.create(name="Chris", gender=1, alive=True)
        p2 = Person.objects.create(name="Chris", gender=2, alive=True)
        p3 = Person.objects.create(name="Bob", gender=1, alive=True)
        link1 = reverse('admin:admin_views_person_change', args=(p1.pk,))
        link2 = reverse('admin:admin_views_person_change', args=(p2.pk,))
        link3 = reverse('admin:admin_views_person_change', args=(p3.pk,))

        # Sort by name, gender
        response = self.client.get(reverse('admin:admin_views_person_changelist'), {'o': '1.2'})
        self.assertContentBefore(response, link3, link1)
        self.assertContentBefore(response, link1, link2)

        # Sort by gender descending, name
        response = self.client.get(reverse('admin:admin_views_person_changelist'), {'o': '-2.1'})
        self.assertContentBefore(response, link2, link3)
        self.assertContentBefore(response, link3, link1)

    def test_change_list_sorting_preserve_queryset_ordering(self):
        """
        If no ordering is defined in `ModelAdmin.ordering` or in the query
        string, then the underlying order of the queryset should not be
        changed, even if it is defined in `Modeladmin.get_queryset()`.
        Refs #11868, #7309.
        """
        p1 = Person.objects.create(name="Amy", gender=1, alive=True, age=80)
        p2 = Person.objects.create(name="Bob", gender=1, alive=True, age=70)
        p3 = Person.objects.create(name="Chris", gender=2, alive=False, age=60)
        link1 = reverse('admin:admin_views_person_change', args=(p1.pk,))
        link2 = reverse('admin:admin_views_person_change', args=(p2.pk,))
        link3 = reverse('admin:admin_views_person_change', args=(p3.pk,))

        response = self.client.get(reverse('admin:admin_views_person_changelist'), {})
        self.assertContentBefore(response, link3, link2)
        self.assertContentBefore(response, link2, link1)

    def test_change_list_sorting_model_meta(self):
        # Test ordering on Model Meta is respected

        l1 = Language.objects.create(iso='ur', name='Urdu')
        l2 = Language.objects.create(iso='ar', name='Arabic')
        link1 = reverse('admin:admin_views_language_change', args=(quote(l1.pk),))
        link2 = reverse('admin:admin_views_language_change', args=(quote(l2.pk),))

        response = self.client.get(reverse('admin:admin_views_language_changelist'), {})
        self.assertContentBefore(response, link2, link1)

        # Test we can override with query string
        response = self.client.get(reverse('admin:admin_views_language_changelist'), {'o': '-1'})
        self.assertContentBefore(response, link1, link2)

    def test_change_list_sorting_override_model_admin(self):
        # Test ordering on Model Admin is respected, and overrides Model Meta
        dt = datetime.datetime.now()
        p1 = Podcast.objects.create(name="A", release_date=dt)
        p2 = Podcast.objects.create(name="B", release_date=dt - datetime.timedelta(10))
        link1 = reverse('admin:admin_views_podcast_change', args=(p1.pk,))
        link2 = reverse('admin:admin_views_podcast_change', args=(p2.pk,))

        response = self.client.get(reverse('admin:admin_views_podcast_changelist'), {})
        self.assertContentBefore(response, link1, link2)

    def test_multiple_sort_same_field(self):
        # Check that we get the columns we expect if we have two columns
        # that correspond to the same ordering field
        dt = datetime.datetime.now()
        p1 = Podcast.objects.create(name="A", release_date=dt)
        p2 = Podcast.objects.create(name="B", release_date=dt - datetime.timedelta(10))
        link1 = reverse('admin:admin_views_podcast_change', args=(quote(p1.pk),))
        link2 = reverse('admin:admin_views_podcast_change', args=(quote(p2.pk),))

        response = self.client.get(reverse('admin:admin_views_podcast_changelist'), {})
        self.assertContentBefore(response, link1, link2)

        p1 = ComplexSortedPerson.objects.create(name="Bob", age=10)
        p2 = ComplexSortedPerson.objects.create(name="Amy", age=20)
        link1 = reverse('admin:admin_views_complexsortedperson_change', args=(p1.pk,))
        link2 = reverse('admin:admin_views_complexsortedperson_change', args=(p2.pk,))

        response = self.client.get(reverse('admin:admin_views_complexsortedperson_changelist'), {})
        # Should have 5 columns (including action checkbox col)
        self.assertContains(response, '<th scope="col"', count=5)

        self.assertContains(response, 'Name')
        self.assertContains(response, 'Colored name')

        # Check order
        self.assertContentBefore(response, 'Name', 'Colored name')

        # Check sorting - should be by name
        self.assertContentBefore(response, link2, link1)

    def test_sort_indicators_admin_order(self):
        """
        Ensures that the admin shows default sort indicators for all
        kinds of 'ordering' fields: field names, method on the model
        admin and model itself, and other callables. See #17252.
        """
        models = [(AdminOrderedField, 'adminorderedfield'),
                  (AdminOrderedModelMethod, 'adminorderedmodelmethod'),
                  (AdminOrderedAdminMethod, 'adminorderedadminmethod'),
                  (AdminOrderedCallable, 'adminorderedcallable')]
        for model, url in models:
            model.objects.create(stuff='The Last Item', order=3)
            model.objects.create(stuff='The First Item', order=1)
            model.objects.create(stuff='The Middle Item', order=2)
            response = self.client.get(reverse('admin:admin_views_%s_changelist' % url), {})
            self.assertEqual(response.status_code, 200)
            # Should have 3 columns including action checkbox col.
            self.assertContains(response, '<th scope="col"', count=3, msg_prefix=url)
            # Check if the correct column was selected. 2 is the index of the
            # 'order' column in the model admin's 'list_display' with 0 being
            # the implicit 'action_checkbox' and 1 being the column 'stuff'.
            self.assertEqual(response.context['cl'].get_ordering_field_columns(), {2: 'asc'})
            # Check order of records.
            self.assertContentBefore(response, 'The First Item', 'The Middle Item')
            self.assertContentBefore(response, 'The Middle Item', 'The Last Item')

    def test_limited_filter(self):
        """Ensure admin changelist filters do not contain objects excluded via limit_choices_to.
        This also tests relation-spanning filters (e.g. 'color__value').
        """
        response = self.client.get(reverse('admin:admin_views_thing_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="changelist-filter">',
            msg_prefix="Expected filter not found in changelist view")
        self.assertNotContains(response, '<a href="?color__id__exact=3">Blue</a>',
            msg_prefix="Changelist filter not correctly limited by limit_choices_to")

    def test_relation_spanning_filters(self):
        changelist_url = reverse('admin:admin_views_chapterxtra1_changelist')
        response = self.client.get(changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="changelist-filter">')
        filters = {
            'chap__id__exact': dict(
                values=[c.id for c in Chapter.objects.all()],
                test=lambda obj, value: obj.chap.id == value),
            'chap__title': dict(
                values=[c.title for c in Chapter.objects.all()],
                test=lambda obj, value: obj.chap.title == value),
            'chap__book__id__exact': dict(
                values=[b.id for b in Book.objects.all()],
                test=lambda obj, value: obj.chap.book.id == value),
            'chap__book__name': dict(
                values=[b.name for b in Book.objects.all()],
                test=lambda obj, value: obj.chap.book.name == value),
            'chap__book__promo__id__exact': dict(
                values=[p.id for p in Promo.objects.all()],
                test=lambda obj, value: obj.chap.book.promo_set.filter(id=value).exists()),
            'chap__book__promo__name': dict(
                values=[p.name for p in Promo.objects.all()],
                test=lambda obj, value: obj.chap.book.promo_set.filter(name=value).exists()),
        }
        for filter_path, params in filters.items():
            for value in params['values']:
                query_string = urlencode({filter_path: value})
                # ensure filter link exists
                self.assertContains(response, '<a href="?%s">' % query_string)
                # ensure link works
                filtered_response = self.client.get('%s?%s' % (changelist_url, query_string))
                self.assertEqual(filtered_response.status_code, 200)
                # ensure changelist contains only valid objects
                for obj in filtered_response.context['cl'].queryset.all():
                    self.assertTrue(params['test'](obj, value))

    def test_incorrect_lookup_parameters(self):
        """Ensure incorrect lookup parameters are handled gracefully."""
        changelist_url = reverse('admin:admin_views_thing_changelist')
        response = self.client.get(changelist_url, {'notarealfield': '5'})
        self.assertRedirects(response, '%s?e=1' % changelist_url)

        # Spanning relationships through a nonexistent related object (Refs #16716)
        response = self.client.get(changelist_url, {'notarealfield__whatever': '5'})
        self.assertRedirects(response, '%s?e=1' % changelist_url)

        response = self.client.get(changelist_url, {'color__id__exact': 'StringNotInteger!'})
        self.assertRedirects(response, '%s?e=1' % changelist_url)

        # Regression test for #18530
        response = self.client.get(changelist_url, {'pub_date__gte': 'foo'})
        self.assertRedirects(response, '%s?e=1' % changelist_url)

    def test_isnull_lookups(self):
        """Ensure is_null is handled correctly."""
        Article.objects.create(title="I Could Go Anywhere", content="Versatile", date=datetime.datetime.now())
        changelist_url = reverse('admin:admin_views_article_changelist')
        response = self.client.get(changelist_url)
        self.assertContains(response, '4 articles')
        response = self.client.get(changelist_url, {'section__isnull': 'false'})
        self.assertContains(response, '3 articles')
        response = self.client.get(changelist_url, {'section__isnull': '0'})
        self.assertContains(response, '3 articles')
        response = self.client.get(changelist_url, {'section__isnull': 'true'})
        self.assertContains(response, '1 article')
        response = self.client.get(changelist_url, {'section__isnull': '1'})
        self.assertContains(response, '1 article')

    def test_logout_and_password_change_URLs(self):
        response = self.client.get(reverse('admin:admin_views_article_changelist'))
        self.assertContains(response, '<a href="%s">' % reverse('admin:logout'))
        self.assertContains(response, '<a href="%s">' % reverse('admin:password_change'))

    def test_named_group_field_choices_change_list(self):
        """
        Ensures the admin changelist shows correct values in the relevant column
        for rows corresponding to instances of a model in which a named group
        has been used in the choices option of a field.
        """
        link1 = reverse('admin:admin_views_fabric_change', args=(1,))
        link2 = reverse('admin:admin_views_fabric_change', args=(2,))
        response = self.client.get(reverse('admin:admin_views_fabric_changelist'))
        fail_msg = "Changelist table isn't showing the right human-readable values set by a model field 'choices' option named group."
        self.assertContains(response, '<a href="%s">Horizontal</a>' % link1, msg_prefix=fail_msg, html=True)
        self.assertContains(response, '<a href="%s">Vertical</a>' % link2, msg_prefix=fail_msg, html=True)

    def test_named_group_field_choices_filter(self):
        """
        Ensures the filter UI shows correctly when at least one named group has
        been used in the choices option of a model field.
        """
        response = self.client.get(reverse('admin:admin_views_fabric_changelist'))
        fail_msg = "Changelist filter isn't showing options contained inside a model field 'choices' option named group."
        self.assertContains(response, '<div id="changelist-filter">')
        self.assertContains(response,
            '<a href="?surface__exact=x">Horizontal</a>', msg_prefix=fail_msg, html=True)
        self.assertContains(response,
            '<a href="?surface__exact=y">Vertical</a>', msg_prefix=fail_msg, html=True)

    def test_change_list_null_boolean_display(self):
        Post.objects.create(public=None)
        response = self.client.get(reverse('admin:admin_views_post_changelist'))
        self.assertContains(response, 'icon-unknown.gif')

    def test_i18n_language_non_english_default(self):
        """
        Check if the JavaScript i18n view returns an empty language catalog
        if the default language is non-English but the selected language
        is English. See #13388 and #3594 for more details.
        """
        with self.settings(LANGUAGE_CODE='fr'), translation.override('en-us'):
            response = self.client.get(reverse('admin:jsi18n'))
            self.assertNotContains(response, 'Choisir une heure')

    def test_i18n_language_non_english_fallback(self):
        """
        Makes sure that the fallback language is still working properly
        in cases where the selected language cannot be found.
        """
        with self.settings(LANGUAGE_CODE='fr'), translation.override('none'):
            response = self.client.get(reverse('admin:jsi18n'))
            self.assertContains(response, 'Choisir une heure')

    def test_L10N_deactivated(self):
        """
        Check if L10N is deactivated, the JavaScript i18n view doesn't
        return localized date/time formats. Refs #14824.
        """
        with self.settings(LANGUAGE_CODE='ru', USE_L10N=False), translation.override('none'):
            response = self.client.get(reverse('admin:jsi18n'))
            self.assertNotContains(response, '%d.%m.%Y %H:%M:%S')
            self.assertContains(response, '%Y-%m-%d %H:%M:%S')

    def test_disallowed_filtering(self):
        with patch_logger('django.security.DisallowedModelAdminLookup', 'error') as calls:
            response = self.client.get(
                "%s?owner__email__startswith=fuzzy" % reverse('admin:admin_views_album_changelist')
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

        # Filters are allowed if explicitly included in list_filter
        response = self.client.get("%s?color__value__startswith=red" % reverse('admin:admin_views_thing_changelist'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get("%s?color__value=red" % reverse('admin:admin_views_thing_changelist'))
        self.assertEqual(response.status_code, 200)

        # Filters should be allowed if they involve a local field without the
        # need to whitelist them in list_filter or date_hierarchy.
        response = self.client.get("%s?age__gt=30" % reverse('admin:admin_views_person_changelist'))
        self.assertEqual(response.status_code, 200)

        e1 = Employee.objects.create(name='Anonymous', gender=1, age=22, alive=True, code='123')
        e2 = Employee.objects.create(name='Visitor', gender=2, age=19, alive=True, code='124')
        WorkHour.objects.create(datum=datetime.datetime.now(), employee=e1)
        WorkHour.objects.create(datum=datetime.datetime.now(), employee=e2)
        response = self.client.get(reverse('admin:admin_views_workhour_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'employee__person_ptr__exact')
        response = self.client.get("%s?employee__person_ptr__exact=%d" % (
            reverse('admin:admin_views_workhour_changelist'), e1.pk)
        )
        self.assertEqual(response.status_code, 200)

    def test_disallowed_to_field(self):
        with patch_logger('django.security.DisallowedModelAdminToField', 'error') as calls:
            response = self.client.get(reverse('admin:admin_views_section_changelist'), {TO_FIELD_VAR: 'missing_field'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

        # Specifying a field that is not referred by any other model registered
        # to this admin site should raise an exception.
        with patch_logger('django.security.DisallowedModelAdminToField', 'error') as calls:
            response = self.client.get(reverse('admin:admin_views_section_changelist'), {TO_FIELD_VAR: 'name'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

        # #23839 - Primary key should always be allowed, even if the referenced model isn't registered.
        response = self.client.get(reverse('admin:admin_views_notreferenced_changelist'), {TO_FIELD_VAR: 'id'})
        self.assertEqual(response.status_code, 200)

        # #23915 - Specifying a field referenced by another model though a m2m should be allowed.
        response = self.client.get(reverse('admin:admin_views_recipe_changelist'), {TO_FIELD_VAR: 'rname'})
        self.assertEqual(response.status_code, 200)

        # #23604, #23915 - Specifying a field referenced through a reverse m2m relationship should be allowed.
        response = self.client.get(reverse('admin:admin_views_ingredient_changelist'), {TO_FIELD_VAR: 'iname'})
        self.assertEqual(response.status_code, 200)

        # #23329 - Specifying a field that is not referred by any other model directly registered
        # to this admin site but registered through inheritance should be allowed.
        response = self.client.get(reverse('admin:admin_views_referencedbyparent_changelist'), {TO_FIELD_VAR: 'name'})
        self.assertEqual(response.status_code, 200)

        # #23431 - Specifying a field that is only referred to by a inline of a registered
        # model should be allowed.
        response = self.client.get(reverse('admin:admin_views_referencedbyinline_changelist'), {TO_FIELD_VAR: 'name'})
        self.assertEqual(response.status_code, 200)

        # We also want to prevent the add, change, and delete views from
        # leaking a disallowed field value.
        with patch_logger('django.security.DisallowedModelAdminToField', 'error') as calls:
            response = self.client.post(reverse('admin:admin_views_section_add'), {TO_FIELD_VAR: 'name'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

        section = Section.objects.create()
        with patch_logger('django.security.DisallowedModelAdminToField', 'error') as calls:
            response = self.client.post(reverse('admin:admin_views_section_change', args=(section.pk,)), {TO_FIELD_VAR: 'name'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

        with patch_logger('django.security.DisallowedModelAdminToField', 'error') as calls:
            response = self.client.post(reverse('admin:admin_views_section_delete', args=(section.pk,)), {TO_FIELD_VAR: 'name'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(len(calls), 1)

    def test_allowed_filtering_15103(self):
        """
        Regressions test for ticket 15103 - filtering on fields defined in a
        ForeignKey 'limit_choices_to' should be allowed, otherwise raw_id_fields
        can break.
        """
        # Filters should be allowed if they are defined on a ForeignKey pointing to this model
        response = self.client.get("%s?leader__name=Palin&leader__age=27" % reverse('admin:admin_views_inquisition_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_popup_dismiss_related(self):
        """
        Regression test for ticket 20664 - ensure the pk is properly quoted.
        """
        actor = Actor.objects.create(name="Palin", age=27)
        response = self.client.get("%s?%s" % (reverse('admin:admin_views_actor_changelist'), IS_POPUP_VAR))
        self.assertContains(response, "opener.dismissRelatedLookupPopup(window, &#39;%s&#39;)" % actor.pk)

    def test_hide_change_password(self):
        """
        Tests if the "change password" link in the admin is hidden if the User
        does not have a usable password set.
        (against 9bea85795705d015cdadc82c68b99196a8554f5c)
        """
        user = User.objects.get(username='super')
        user.set_unusable_password()
        user.save()

        response = self.client.get(reverse('admin:index'))
        self.assertNotContains(response, reverse('admin:password_change'),
            msg_prefix='The "change password" link should not be displayed if a user does not have a usable password.')

    def test_change_view_with_show_delete_extra_context(self):
        """
        Ensured that the 'show_delete' context variable in the admin's change
        view actually controls the display of the delete button.
        Refs #10057.
        """
        instance = UndeletableObject.objects.create(name='foo')
        response = self.client.get(reverse('admin:admin_views_undeletableobject_change', args=(instance.pk,)))
        self.assertNotContains(response, 'deletelink')

    def test_allows_attributeerror_to_bubble_up(self):
        """
        Ensure that AttributeErrors are allowed to bubble when raised inside
        a change list view.

        Requires a model to be created so there's something to be displayed

        Refs: #16655, #18593, and #18747
        """
        Simple.objects.create()
        with self.assertRaises(AttributeError):
            self.client.get(reverse('admin:admin_views_simple_changelist'))

    def test_changelist_with_no_change_url(self):
        """
        ModelAdmin.changelist_view shouldn't result in a NoReverseMatch if url
        for change_view is removed from get_urls

        Regression test for #20934
        """
        UnchangeableObject.objects.create()
        response = self.client.get(reverse('admin:admin_views_unchangeableobject_changelist'))
        self.assertEqual(response.status_code, 200)
        # Check the format of the shown object -- shouldn't contain a change link
        self.assertContains(response, '<th class="field-__str__">UnchangeableObject object</th>', html=True)

    def test_invalid_appindex_url(self):
        """
        #21056 -- URL reversing shouldn't work for nonexistent apps.
        """
        good_url = '/test_admin/admin/admin_views/'
        confirm_good_url = reverse('admin:app_list',
                                   kwargs={'app_label': 'admin_views'})
        self.assertEqual(good_url, confirm_good_url)

        with self.assertRaises(NoReverseMatch):
            reverse('admin:app_list', kwargs={'app_label': 'this_should_fail'})
        with self.assertRaises(NoReverseMatch):
            reverse('admin:app_list', args=('admin_views2',))

    def test_proxy_model_content_type_is_used_for_log_entries(self):
        """
        Log entries for proxy models should have the proxy model's content
        type.

        Regression test for #21084.
        """
        color2_content_type = ContentType.objects.get_for_model(Color2, for_concrete_model=False)

        # add
        color2_add_url = reverse('admin:admin_views_color2_add')
        self.client.post(color2_add_url, {'value': 'orange'})

        color2_addition_log = LogEntry.objects.all()[0]
        self.assertEqual(color2_content_type, color2_addition_log.content_type)

        # change
        color_id = color2_addition_log.object_id
        color2_change_url = reverse('admin:admin_views_color2_change', args=(color_id,))

        self.client.post(color2_change_url, {'value': 'blue'})

        color2_change_log = LogEntry.objects.all()[0]
        self.assertEqual(color2_content_type, color2_change_log.content_type)

        # delete
        color2_delete_url = reverse('admin:admin_views_color2_delete', args=(color_id,))
        self.client.post(color2_delete_url)

        color2_delete_log = LogEntry.objects.all()[0]
        self.assertEqual(color2_content_type, color2_delete_log.content_type)

    def test_adminsite_display_site_url(self):
        """
        #13749 - Admin should display link to front-end site 'View site'
        """
        url = reverse('admin:index')
        response = self.client.get(url)
        self.assertEqual(response.context['site_url'], '/my-site-url/')
        self.assertContains(response, '<a href="/my-site-url/">View site</a>')


@override_settings(TEMPLATES=[{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    # Put this app's templates dir in DIRS to take precedence over the admin's
    # templates dir.
    'DIRS': [os.path.join(os.path.dirname(upath(__file__)), 'templates')],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}])
class AdminCustomTemplateTests(AdminViewBasicTestCase):
    def test_extended_bodyclass_template_change_form(self):
        """
        Ensure that the admin/change_form.html template uses block.super in the
        bodyclass block.
        """
        response = self.client.get(reverse('admin:admin_views_section_add'))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_template_change_password(self):
        """
        Ensure that the auth/user/change_password.html template uses block
        super in the bodyclass block.
        """
        user = User.objects.get(username='super')
        response = self.client.get(reverse('admin:auth_user_password_change', args=(user.id,)))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_template_index(self):
        """
        Ensure that the admin/index.html template uses block.super in the
        bodyclass block.
        """
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_change_list(self):
        """
        Ensure that the admin/change_list.html' template uses block.super
        in the bodyclass block.
        """
        response = self.client.get(reverse('admin:admin_views_article_changelist'))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_template_login(self):
        """
        Ensure that the admin/login.html template uses block.super in the
        bodyclass block.
        """
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_template_delete_confirmation(self):
        """
        Ensure that the admin/delete_confirmation.html template uses
        block.super in the bodyclass block.
        """
        group = Group.objects.create(name="foogroup")
        response = self.client.get(reverse('admin:auth_group_delete', args=(group.id,)))
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_extended_bodyclass_template_delete_selected_confirmation(self):
        """
        Ensure that the admin/delete_selected_confirmation.html template uses
        block.super in bodyclass block.
        """
        group = Group.objects.create(name="foogroup")
        post_data = {
            'action': 'delete_selected',
            'selected_across': '0',
            'index': '0',
            '_selected_action': group.id
        }
        response = self.client.post(reverse('admin:auth_group_changelist'), post_data)
        self.assertEqual(response.context['site_header'], 'Django administration')
        self.assertContains(response, 'bodyclass_consistency_check ')

    def test_filter_with_custom_template(self):
        """
        Ensure that one can use a custom template to render an admin filter.
        Refs #17515.
        """
        response = self.client.get(reverse('admin:admin_views_color2_changelist'))
        self.assertTemplateUsed(response, 'custom_filter_template.html')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
                   ROOT_URLCONF="admin_views.urls")
class AdminViewFormUrlTest(TestCase):
    fixtures = ["admin-views-users.xml"]
    current_app = "admin3"

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_change_form_URL_has_correct_value(self):
        """
        Tests whether change_view has form_url in response.context
        """
        response = self.client.get(
            reverse('admin:admin_views_section_change', args=(1,), current_app=self.current_app)
        )
        self.assertIn('form_url', response.context, msg='form_url not present in response.context')
        self.assertEqual(response.context['form_url'], 'pony')

    def test_initial_data_can_be_overridden(self):
        """
        Tests that the behavior for setting initial
        form data can be overridden in the ModelAdmin class.

        Usually, the initial value is set via the GET params.
        """
        response = self.client.get(
            reverse('admin:admin_views_restaurant_add', current_app=self.current_app),
            {'name': 'test_value'}
        )
        # this would be the usual behaviour
        self.assertNotContains(response, 'value="test_value"')
        # this is the overridden behaviour
        self.assertContains(response, 'value="overridden_value"')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
                   ROOT_URLCONF="admin_views.urls")
class AdminJavaScriptTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_js_minified_only_if_debug_is_false(self):
        """
        Ensure that the minified versions of the JS files are only used when
        DEBUG is False.
        Refs #17521.
        """
        with override_settings(DEBUG=False):
            response = self.client.get(reverse('admin:admin_views_section_add'))
            self.assertNotContains(response, 'jquery.js')
            self.assertContains(response, 'jquery.min.js')
            self.assertNotContains(response, 'prepopulate.js')
            self.assertContains(response, 'prepopulate.min.js')
            self.assertNotContains(response, 'actions.js')
            self.assertContains(response, 'actions.min.js')
            self.assertNotContains(response, 'collapse.js')
            self.assertContains(response, 'collapse.min.js')
            self.assertNotContains(response, 'inlines.js')
            self.assertContains(response, 'inlines.min.js')
        with override_settings(DEBUG=True):
            response = self.client.get(reverse('admin:admin_views_section_add'))
            self.assertContains(response, 'jquery.js')
            self.assertNotContains(response, 'jquery.min.js')
            self.assertContains(response, 'prepopulate.js')
            self.assertNotContains(response, 'prepopulate.min.js')
            self.assertContains(response, 'actions.js')
            self.assertNotContains(response, 'actions.min.js')
            self.assertContains(response, 'collapse.js')
            self.assertNotContains(response, 'collapse.min.js')
            self.assertContains(response, 'inlines.js')
            self.assertNotContains(response, 'inlines.min.js')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class SaveAsTests(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-person.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_save_as_duplication(self):
        """Ensure save as actually creates a new person"""
        post_data = {'_saveasnew': '', 'name': 'John M', 'gender': 1, 'age': 42}
        self.client.post(reverse('admin:admin_views_person_change', args=(1,)), post_data)
        self.assertEqual(len(Person.objects.filter(name='John M')), 1)
        self.assertEqual(len(Person.objects.filter(id=1)), 1)

    def test_save_as_display(self):
        """
        Ensure that 'save as' is displayed when activated and after submitting
        invalid data aside save_as_new will not show us a form to overwrite the
        initial model.
        """
        change_url = reverse('admin:admin_views_person_change', args=(1,))
        response = self.client.get(change_url)
        self.assertTrue(response.context['save_as'])
        post_data = {'_saveasnew': '', 'name': 'John M', 'gender': 3, 'alive': 'checked'}
        response = self.client.post(change_url, post_data)
        self.assertEqual(response.context['form_url'], reverse('admin:admin_views_person_add'))


@override_settings(ROOT_URLCONF="admin_views.urls")
class CustomModelAdminTest(AdminViewBasicTestCase):

    def test_custom_admin_site_login_form(self):
        self.client.logout()
        response = self.client.get(reverse('admin2:index'), follow=True)
        self.assertIsInstance(response, TemplateResponse)
        self.assertEqual(response.status_code, 200)
        login = self.client.post(reverse('admin2:login'), {
            REDIRECT_FIELD_NAME: reverse('admin2:index'),
            'username': 'customform',
            'password': 'secret',
        }, follow=True)
        self.assertIsInstance(login, TemplateResponse)
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, 'custom form error')

    def test_custom_admin_site_login_template(self):
        self.client.logout()
        response = self.client.get(reverse('admin2:index'), follow=True)
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/login.html')
        self.assertContains(response, 'Hello from a custom login template')

    def test_custom_admin_site_logout_template(self):
        response = self.client.get(reverse('admin2:logout'))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/logout.html')
        self.assertContains(response, 'Hello from a custom logout template')

    def test_custom_admin_site_index_view_and_template(self):
        try:
            response = self.client.get(reverse('admin2:index'))
        except TypeError:
            self.fail('AdminSite.index_template should accept a list of template paths')
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/index.html')
        self.assertContains(response, 'Hello from a custom index template *bar*')

    def test_custom_admin_site_app_index_view_and_template(self):
        response = self.client.get(reverse('admin2:app_list', args=('admin_views',)))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/app_index.html')
        self.assertContains(response, 'Hello from a custom app_index template')

    def test_custom_admin_site_password_change_template(self):
        response = self.client.get(reverse('admin2:password_change'))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/password_change_form.html')
        self.assertContains(response, 'Hello from a custom password change form template')

    def test_custom_admin_site_password_change_with_extra_context(self):
        response = self.client.get(reverse('admin2:password_change'))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/password_change_form.html')
        self.assertContains(response, 'eggs')

    def test_custom_admin_site_password_change_done_template(self):
        response = self.client.get(reverse('admin2:password_change_done'))
        self.assertIsInstance(response, TemplateResponse)
        self.assertTemplateUsed(response, 'custom_admin/password_change_done.html')
        self.assertContains(response, 'Hello from a custom password change done template')

    def test_custom_admin_site_view(self):
        self.client.login(username='super', password='secret')
        response = self.client.get(reverse('admin2:my_view'))
        self.assertEqual(response.content, b"Django is a magical pony!")

    def test_pwd_change_custom_template(self):
        self.client.login(username='super', password='secret')
        su = User.objects.get(username='super')
        try:
            response = self.client.get(
                reverse('admin4:auth_user_password_change', args=(su.pk,))
            )
        except TypeError:
            self.fail('ModelAdmin.change_user_password_template should accept a list of template paths')
        self.assertEqual(response.status_code, 200)


def get_perm(Model, perm):
    """Return the permission object, for the Model"""
    ct = ContentType.objects.get_for_model(Model)
    return Permission.objects.get(content_type=ct, codename=perm)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewPermissionsTest(TestCase):
    """Tests for Admin Views Permissions."""

    fixtures = ['admin-views-users.xml']

    def setUp(self):
        """Test setup."""
        # Setup permissions, for our users who can add, change, and delete.
        # We can't put this into the fixture, because the content type id
        # and the permission id could be different on each run of the test.

        opts = Article._meta

        # User who can add Articles
        add_user = User.objects.get(username='adduser')
        add_user.user_permissions.add(get_perm(Article,
            get_permission_codename('add', opts)))

        # User who can change Articles
        change_user = User.objects.get(username='changeuser')
        change_user.user_permissions.add(get_perm(Article,
            get_permission_codename('change', opts)))
        change_user2 = User.objects.get(username='nostaff')
        change_user2.user_permissions.add(get_perm(Article,
            get_permission_codename('change', opts)))

        # User who can delete Articles
        delete_user = User.objects.get(username='deleteuser')
        delete_user.user_permissions.add(get_perm(Article,
            get_permission_codename('delete', opts)))

        delete_user.user_permissions.add(get_perm(Section,
            get_permission_codename('delete', Section._meta)))

        # login POST dicts
        self.index_url = reverse('admin:index')
        self.super_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'super',
            'password': 'secret',
        }
        self.super_email_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'super@example.com',
            'password': 'secret',
        }
        self.super_email_bad_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'super@example.com',
            'password': 'notsecret',
        }
        self.adduser_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'adduser',
            'password': 'secret',
        }
        self.changeuser_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'changeuser',
            'password': 'secret',
        }
        self.deleteuser_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'deleteuser',
            'password': 'secret',
        }
        self.nostaff_login = {
            REDIRECT_FIELD_NAME: reverse('has_permission_admin:index'),
            'username': 'nostaff',
            'password': 'secret',
        }
        self.joepublic_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'username': 'joepublic',
            'password': 'secret',
        }
        self.no_username_login = {
            REDIRECT_FIELD_NAME: self.index_url,
            'password': 'secret',
        }

    def test_login(self):
        """
        Make sure only staff members can log in.

        Successful posts to the login page will redirect to the original url.
        Unsuccessful attempts will continue to render the login page with
        a 200 status code.
        """
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        # Super User
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.super_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)
        self.client.get(reverse('admin:logout'))

        # Test if user enters email address
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.super_email_login)
        self.assertContains(login, ERROR_MESSAGE)
        # only correct passwords get a username hint
        login = self.client.post(login_url, self.super_email_bad_login)
        self.assertContains(login, ERROR_MESSAGE)
        new_user = User(username='jondoe', password='secret', email='super@example.com')
        new_user.save()
        # check to ensure if there are multiple email addresses a user doesn't get a 500
        login = self.client.post(login_url, self.super_email_login)
        self.assertContains(login, ERROR_MESSAGE)

        # Add User
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.adduser_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)
        self.client.get(reverse('admin:logout'))

        # Change User
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.changeuser_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)
        self.client.get(reverse('admin:logout'))

        # Delete User
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.deleteuser_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)
        self.client.get(reverse('admin:logout'))

        # Regular User should not be able to login.
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.joepublic_login)
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, ERROR_MESSAGE)

        # Requests without username should not return 500 errors.
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        login = self.client.post(login_url, self.no_username_login)
        self.assertEqual(login.status_code, 200)
        form = login.context[0].get('form')
        self.assertEqual(form.errors['username'][0], 'This field is required.')

    def test_login_has_permission(self):
        # Regular User should not be able to login.
        response = self.client.get(reverse('has_permission_admin:index'))
        self.assertEqual(response.status_code, 302)
        login = self.client.post(reverse('has_permission_admin:login'), self.joepublic_login)
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, 'permission denied')

        # User with permissions should be able to login.
        response = self.client.get(reverse('has_permission_admin:index'))
        self.assertEqual(response.status_code, 302)
        login = self.client.post(reverse('has_permission_admin:login'), self.nostaff_login)
        self.assertRedirects(login, reverse('has_permission_admin:index'))
        self.assertFalse(login.context)
        self.client.get(reverse('has_permission_admin:logout'))

        # Staff should be able to login.
        response = self.client.get(reverse('has_permission_admin:index'))
        self.assertEqual(response.status_code, 302)
        login = self.client.post(reverse('has_permission_admin:login'), {
            REDIRECT_FIELD_NAME: reverse('has_permission_admin:index'),
            'username': 'deleteuser',
            'password': 'secret',
        })
        self.assertRedirects(login, reverse('has_permission_admin:index'))
        self.assertFalse(login.context)
        self.client.get(reverse('has_permission_admin:logout'))

    def test_login_successfully_redirects_to_original_URL(self):
        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)
        query_string = 'the-answer=42'
        redirect_url = '%s?%s' % (self.index_url, query_string)
        new_next = {REDIRECT_FIELD_NAME: redirect_url}
        post_data = self.super_login.copy()
        post_data.pop(REDIRECT_FIELD_NAME)
        login = self.client.post(
            '%s?%s' % (reverse('admin:login'), urlencode(new_next)),
            post_data)
        self.assertRedirects(login, redirect_url)

    def test_double_login_is_not_allowed(self):
        """Regression test for #19327"""
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))

        response = self.client.get(self.index_url)
        self.assertEqual(response.status_code, 302)

        # Establish a valid admin session
        login = self.client.post(login_url, self.super_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)

        # Logging in with non-admin user fails
        login = self.client.post(login_url, self.joepublic_login)
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, ERROR_MESSAGE)

        # Establish a valid admin session
        login = self.client.post(login_url, self.super_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)

        # Logging in with admin user while already logged in
        login = self.client.post(login_url, self.super_login)
        self.assertRedirects(login, self.index_url)
        self.assertFalse(login.context)
        self.client.get(reverse('admin:logout'))

    def test_add_view(self):
        """Test add view restricts access and actually adds items."""

        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        add_dict = {'title': 'Døm ikke',
                    'content': '<p>great article</p>',
                    'date_0': '2008-03-18', 'date_1': '10:54:39',
                    'section': 1}

        # Change User should not have access to add articles
        self.client.get(self.index_url)
        self.client.post(login_url, self.changeuser_login)
        # make sure the view removes test cookie
        self.assertEqual(self.client.session.test_cookie_worked(), False)
        response = self.client.get(reverse('admin:admin_views_article_add'))
        self.assertEqual(response.status_code, 403)
        # Try POST just to make sure
        post = self.client.post(reverse('admin:admin_views_article_add'), add_dict)
        self.assertEqual(post.status_code, 403)
        self.assertEqual(Article.objects.all().count(), 3)
        self.client.get(reverse('admin:logout'))

        # Add user may login and POST to add view, then redirect to admin root
        self.client.get(self.index_url)
        self.client.post(login_url, self.adduser_login)
        addpage = self.client.get(reverse('admin:admin_views_article_add'))
        change_list_link = '&rsaquo; <a href="%s">Articles</a>' % reverse('admin:admin_views_article_changelist')
        self.assertNotContains(addpage, change_list_link,
            msg_prefix='User restricted to add permission is given link to change list view in breadcrumbs.')
        post = self.client.post(reverse('admin:admin_views_article_add'), add_dict)
        self.assertRedirects(post, self.index_url)
        self.assertEqual(Article.objects.all().count(), 4)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Greetings from a created object')
        self.client.get(reverse('admin:logout'))

        # Super can add too, but is redirected to the change list view
        self.client.get(self.index_url)
        self.client.post(login_url, self.super_login)
        addpage = self.client.get(reverse('admin:admin_views_article_add'))
        self.assertContains(addpage, change_list_link,
            msg_prefix='Unrestricted user is not given link to change list view in breadcrumbs.')
        post = self.client.post(reverse('admin:admin_views_article_add'), add_dict)
        self.assertRedirects(post, reverse('admin:admin_views_article_changelist'))
        self.assertEqual(Article.objects.all().count(), 5)
        self.client.get(reverse('admin:logout'))

        # 8509 - if a normal user is already logged in, it is possible
        # to change user into the superuser without error
        self.client.login(username='joepublic', password='secret')
        # Check and make sure that if user expires, data still persists
        self.client.get(self.index_url)
        self.client.post(login_url, self.super_login)
        # make sure the view removes test cookie
        self.assertEqual(self.client.session.test_cookie_worked(), False)

    def test_change_view(self):
        """Change view should restrict access and allow users to edit items."""

        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        change_dict = {'title': 'Ikke fordømt',
                       'content': '<p>edited article</p>',
                       'date_0': '2008-03-18', 'date_1': '10:54:39',
                       'section': 1}
        article_change_url = reverse('admin:admin_views_article_change', args=(1,))
        article_changelist_url = reverse('admin:admin_views_article_changelist')

        # add user should not be able to view the list of article or change any of them
        self.client.get(self.index_url)
        self.client.post(login_url, self.adduser_login)
        response = self.client.get(article_changelist_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(article_change_url)
        self.assertEqual(response.status_code, 403)
        post = self.client.post(article_change_url, change_dict)
        self.assertEqual(post.status_code, 403)
        self.client.get(reverse('admin:logout'))

        # change user can view all items and edit them
        self.client.get(self.index_url)
        self.client.post(login_url, self.changeuser_login)
        response = self.client.get(article_changelist_url)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(article_change_url)
        self.assertEqual(response.status_code, 200)
        post = self.client.post(article_change_url, change_dict)
        self.assertRedirects(post, article_changelist_url)
        self.assertEqual(Article.objects.get(pk=1).content, '<p>edited article</p>')

        # one error in form should produce singular error message, multiple errors plural
        change_dict['title'] = ''
        post = self.client.post(article_change_url, change_dict)
        self.assertContains(post, 'Please correct the error below.',
            msg_prefix='Singular error message not found in response to post with one error')

        change_dict['content'] = ''
        post = self.client.post(article_change_url, change_dict)
        self.assertContains(post, 'Please correct the errors below.',
            msg_prefix='Plural error message not found in response to post with multiple errors')
        self.client.get(reverse('admin:logout'))

        # Test redirection when using row-level change permissions. Refs #11513.
        r1 = RowLevelChangePermissionModel.objects.create(id=1, name="odd id")
        r2 = RowLevelChangePermissionModel.objects.create(id=2, name="even id")
        change_url_1 = reverse('admin:admin_views_rowlevelchangepermissionmodel_change', args=(r1.pk,))
        change_url_2 = reverse('admin:admin_views_rowlevelchangepermissionmodel_change', args=(r2.pk,))
        for login_dict in [self.super_login, self.changeuser_login, self.adduser_login, self.deleteuser_login]:
            self.client.post(login_url, login_dict)
            response = self.client.get(change_url_1)
            self.assertEqual(response.status_code, 403)
            response = self.client.post(change_url_1, {'name': 'changed'})
            self.assertEqual(RowLevelChangePermissionModel.objects.get(id=1).name, 'odd id')
            self.assertEqual(response.status_code, 403)
            response = self.client.get(change_url_2)
            self.assertEqual(response.status_code, 200)
            response = self.client.post(change_url_2, {'name': 'changed'})
            self.assertEqual(RowLevelChangePermissionModel.objects.get(id=2).name, 'changed')
            self.assertRedirects(response, self.index_url)
            self.client.get(reverse('admin:logout'))

        for login_dict in [self.joepublic_login, self.no_username_login]:
            self.client.post(login_url, login_dict)
            response = self.client.get(change_url_1, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')
            response = self.client.post(change_url_1, {'name': 'changed'}, follow=True)
            self.assertEqual(RowLevelChangePermissionModel.objects.get(id=1).name, 'odd id')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')
            response = self.client.get(change_url_2, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')
            response = self.client.post(change_url_2, {'name': 'changed again'}, follow=True)
            self.assertEqual(RowLevelChangePermissionModel.objects.get(id=2).name, 'changed')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')
            self.client.get(reverse('admin:logout'))

    def test_history_view(self):
        """History view should restrict access."""

        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))

        # add user should not be able to view the list of article or change any of them
        self.client.get(self.index_url)
        self.client.post(login_url, self.adduser_login)
        response = self.client.get(reverse('admin:admin_views_article_history', args=(1,)))
        self.assertEqual(response.status_code, 403)
        self.client.get(reverse('admin:logout'))

        # change user can view all items and edit them
        self.client.get(self.index_url)
        self.client.post(login_url, self.changeuser_login)
        response = self.client.get(reverse('admin:admin_views_article_history', args=(1,)))
        self.assertEqual(response.status_code, 200)

        # Test redirection when using row-level change permissions. Refs #11513.
        RowLevelChangePermissionModel.objects.create(id=1, name="odd id")
        RowLevelChangePermissionModel.objects.create(id=2, name="even id")
        for login_dict in [self.super_login, self.changeuser_login, self.adduser_login, self.deleteuser_login]:
            self.client.post(login_url, login_dict)
            response = self.client.get(reverse('admin:admin_views_rowlevelchangepermissionmodel_history', args=(1,)))
            self.assertEqual(response.status_code, 403)

            response = self.client.get(reverse('admin:admin_views_rowlevelchangepermissionmodel_history', args=(2,)))
            self.assertEqual(response.status_code, 200)

            self.client.get(reverse('admin:logout'))

        for login_dict in [self.joepublic_login, self.no_username_login]:
            self.client.post(login_url, login_dict)
            response = self.client.get(
                reverse('admin:admin_views_rowlevelchangepermissionmodel_history', args=(1,)), follow=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')
            response = self.client.get(
                reverse('admin:admin_views_rowlevelchangepermissionmodel_history', args=(2,)), follow=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'login-form')

            self.client.get(reverse('admin:logout'))

    def test_history_view_bad_url(self):
        self.client.post(reverse('admin:login'), self.changeuser_login)
        response = self.client.get(reverse('admin:admin_views_article_history', args=('foo',)))
        self.assertEqual(response.status_code, 404)

    def test_conditionally_show_add_section_link(self):
        """
        The foreign key widget should only show the "add related" button if the
        user has permission to add that related item.
        """
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        # Set up and log in user.
        url = reverse('admin:admin_views_article_add')
        add_link_text = 'add_id_section'
        self.client.post(login_url, self.adduser_login)
        # The user can't add sections yet, so they shouldn't see the "add
        # section" link.
        response = self.client.get(url)
        self.assertNotContains(response, add_link_text)
        # Allow the user to add sections too. Now they can see the "add
        # section" link.
        user = User.objects.get(username='adduser')
        perm = get_perm(Section, get_permission_codename('add', Section._meta))
        user.user_permissions.add(perm)
        response = self.client.get(url)
        self.assertContains(response, add_link_text)

    def test_conditionally_show_change_section_link(self):
        """
        The foreign key widget should only show the "change related" button if
        the user has permission to change that related item.
        """
        def get_change_related(response):
            return response.context['adminform'].form.fields['section'].widget.can_change_related

        login_url = reverse('admin:login')
        # Set up and log in user.
        url = reverse('admin:admin_views_article_add')
        change_link_text = 'change_id_section'
        self.client.post(login_url, self.adduser_login)
        # The user can't change sections yet, so they shouldn't see the "change
        # section" link.
        response = self.client.get(url)
        self.assertFalse(get_change_related(response))
        self.assertNotContains(response, change_link_text)
        # Allow the user to change sections too. Now they can see the "change
        # section" link.
        user = User.objects.get(username='adduser')
        perm = get_perm(Section, get_permission_codename('change', Section._meta))
        user.user_permissions.add(perm)
        response = self.client.get(url)
        self.assertTrue(get_change_related(response))
        self.assertContains(response, change_link_text)

    def test_conditionally_show_delete_section_link(self):
        """
        The foreign key widget should only show the "delete related" button if
        the user has permission to delete that related item.
        """
        def get_delete_related(response):
            return response.context['adminform'].form.fields['sub_section'].widget.can_delete_related

        login_url = reverse('admin:login')
        # Set up and log in user.
        url = reverse('admin:admin_views_article_add')
        delete_link_text = 'delete_id_sub_section'
        self.client.get(self.index_url)
        self.client.post(login_url, self.adduser_login)
        # The user can't delete sections yet, so they shouldn't see the "delete
        # section" link.
        response = self.client.get(url)
        self.assertFalse(get_delete_related(response))
        self.assertNotContains(response, delete_link_text)
        # Allow the user to delete sections too. Now they can see the "delete
        # section" link.
        user = User.objects.get(username='adduser')
        perm = get_perm(Section, get_permission_codename('delete', Section._meta))
        user.user_permissions.add(perm)
        response = self.client.get(url)
        self.assertTrue(get_delete_related(response))
        self.assertContains(response, delete_link_text)

    def test_custom_model_admin_templates(self):
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        self.client.get(self.index_url)
        self.client.post(login_url, self.super_login)

        # Test custom change list template with custom extra context
        response = self.client.get(reverse('admin:admin_views_customarticle_changelist'))
        self.assertContains(response, "var hello = 'Hello!';")
        self.assertTemplateUsed(response, 'custom_admin/change_list.html')

        # Test custom add form template
        response = self.client.get(reverse('admin:admin_views_customarticle_add'))
        self.assertTemplateUsed(response, 'custom_admin/add_form.html')

        # Add an article so we can test delete, change, and history views
        post = self.client.post(reverse('admin:admin_views_customarticle_add'), {
            'content': '<p>great article</p>',
            'date_0': '2008-03-18',
            'date_1': '10:54:39'
        })
        self.assertRedirects(post, reverse('admin:admin_views_customarticle_changelist'))
        self.assertEqual(CustomArticle.objects.all().count(), 1)
        article_pk = CustomArticle.objects.all()[0].pk

        # Test custom delete, change, and object history templates
        # Test custom change form template
        response = self.client.get(reverse('admin:admin_views_customarticle_change', args=(article_pk,)))
        self.assertTemplateUsed(response, 'custom_admin/change_form.html')
        response = self.client.get(reverse('admin:admin_views_customarticle_delete', args=(article_pk,)))
        self.assertTemplateUsed(response, 'custom_admin/delete_confirmation.html')
        response = self.client.post(reverse('admin:admin_views_customarticle_changelist'), data={
            'index': 0,
            'action': ['delete_selected'],
            '_selected_action': ['1'],
        })
        self.assertTemplateUsed(response, 'custom_admin/delete_selected_confirmation.html')
        response = self.client.get(reverse('admin:admin_views_customarticle_history', args=(article_pk,)))
        self.assertTemplateUsed(response, 'custom_admin/object_history.html')

        self.client.get(reverse('admin:logout'))

    def test_delete_view(self):
        """Delete view should restrict access and actually delete items."""

        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        delete_dict = {'post': 'yes'}
        delete_url = reverse('admin:admin_views_article_delete', args=(1,))

        # add user should not be able to delete articles
        self.client.get(self.index_url)
        self.client.post(login_url, self.adduser_login)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 403)
        post = self.client.post(delete_url, delete_dict)
        self.assertEqual(post.status_code, 403)
        self.assertEqual(Article.objects.all().count(), 3)
        self.client.get(reverse('admin:logout'))

        # Delete user can delete
        self.client.get(self.index_url)
        self.client.post(login_url, self.deleteuser_login)
        response = self.client.get(reverse('admin:admin_views_section_delete', args=(1,)))
        self.assertContains(response, "<h2>Summary</h2>")
        self.assertContains(response, "<li>Articles: 3</li>")
        # test response contains link to related Article
        self.assertContains(response, "admin_views/article/1/")

        response = self.client.get(delete_url)
        self.assertContains(response, "admin_views/article/1/")
        self.assertContains(response, "<h2>Summary</h2>")
        self.assertContains(response, "<li>Articles: 1</li>")
        self.assertEqual(response.status_code, 200)
        post = self.client.post(delete_url, delete_dict)
        self.assertRedirects(post, self.index_url)
        self.assertEqual(Article.objects.all().count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Greetings from a deleted object')
        article_ct = ContentType.objects.get_for_model(Article)
        logged = LogEntry.objects.get(content_type=article_ct, action_flag=DELETION)
        self.assertEqual(logged.object_id, '1')
        self.client.get(reverse('admin:logout'))

    def test_disabled_permissions_when_logged_in(self):
        self.client.login(username='super', password='secret')
        superuser = User.objects.get(username='super')
        superuser.is_active = False
        superuser.save()

        response = self.client.get(self.index_url, follow=True)
        self.assertContains(response, 'id="login-form"')
        self.assertNotContains(response, 'Log out')

        response = self.client.get(reverse('secure_view'), follow=True)
        self.assertContains(response, 'id="login-form"')

    def test_disabled_staff_permissions_when_logged_in(self):
        self.client.login(username='super', password='secret')
        superuser = User.objects.get(username='super')
        superuser.is_staff = False
        superuser.save()

        response = self.client.get(self.index_url, follow=True)
        self.assertContains(response, 'id="login-form"')
        self.assertNotContains(response, 'Log out')

        response = self.client.get(reverse('secure_view'), follow=True)
        self.assertContains(response, 'id="login-form"')

    def test_app_index_fail_early(self):
        """
        If a user has no module perms, avoid iterating over all the modeladmins
        in the registry.
        """
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))
        opts = Article._meta
        change_user = User.objects.get(username='changeuser')
        permission = get_perm(Article, get_permission_codename('change', opts))

        self.client.post(login_url, self.changeuser_login)

        # the user has no module permissions, because this module doesn't exist
        change_user.user_permissions.remove(permission)
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertEqual(response.status_code, 403)

        # the user now has module permissions
        change_user.user_permissions.add(permission)
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertEqual(response.status_code, 200)

    def test_shortcut_view_only_available_to_staff(self):
        """
        Only admin users should be able to use the admin shortcut view.
        """
        model_ctype = ContentType.objects.get_for_model(ModelWithStringPrimaryKey)
        obj = ModelWithStringPrimaryKey.objects.create(string_pk='foo')
        shortcut_url = reverse('admin:view_on_site', args=(model_ctype.pk, obj.pk))

        # Not logged in: we should see the login page.
        response = self.client.get(shortcut_url, follow=True)
        self.assertTemplateUsed(response, 'admin/login.html')

        # Logged in? Redirect.
        self.client.login(username='super', password='secret')
        response = self.client.get(shortcut_url, follow=False)
        # Can't use self.assertRedirects() because User.get_absolute_url() is silly.
        self.assertEqual(response.status_code, 302)
        # Domain may depend on contrib.sites tests also run
        six.assertRegex(self, response.url, 'http://(testserver|example.com)/dummy/foo/')

    def test_has_module_permission(self):
        """
        Ensure that has_module_permission() returns True for all users who
        have any permission for that module (add, change, or delete), so that
        the module is displayed on the admin index page.
        """
        login_url = '%s?next=%s' % (reverse('admin:login'), reverse('admin:index'))

        self.client.post(login_url, self.super_login)
        response = self.client.get(self.index_url)
        self.assertContains(response, 'admin_views')
        self.assertContains(response, 'Articles')
        self.client.get(reverse('admin:logout'))

        self.client.post(login_url, self.adduser_login)
        response = self.client.get(self.index_url)
        self.assertContains(response, 'admin_views')
        self.assertContains(response, 'Articles')
        self.client.get(reverse('admin:logout'))

        self.client.post(login_url, self.changeuser_login)
        response = self.client.get(self.index_url)
        self.assertContains(response, 'admin_views')
        self.assertContains(response, 'Articles')
        self.client.get(reverse('admin:logout'))

        self.client.post(login_url, self.deleteuser_login)
        response = self.client.get(self.index_url)
        self.assertContains(response, 'admin_views')
        self.assertContains(response, 'Articles')
        self.client.get(reverse('admin:logout'))

    def test_overriding_has_module_permission(self):
        """
        Ensure that overriding has_module_permission() has the desired effect.
        In this case, it always returns False, so the module should not be
        displayed on the admin index page for any users.
        """
        login_url = '%s?next=%s' % (reverse('admin7:login'), reverse('admin7:index'))
        index_url = reverse('admin7:index')

        self.client.post(login_url, self.super_login)
        response = self.client.get(index_url)
        self.assertNotContains(response, 'admin_views')
        self.assertNotContains(response, 'Articles')
        self.client.get(reverse('admin7:logout'))

        self.client.post(login_url, self.adduser_login)
        response = self.client.get(index_url)
        self.assertNotContains(response, 'admin_views')
        self.assertNotContains(response, 'Articles')
        self.client.get(reverse('admin7:logout'))

        self.client.post(login_url, self.changeuser_login)
        response = self.client.get(index_url)
        self.assertNotContains(response, 'admin_views')
        self.assertNotContains(response, 'Articles')
        self.client.get(reverse('admin7:logout'))

        self.client.post(login_url, self.deleteuser_login)
        response = self.client.get(index_url)
        self.assertNotContains(response, 'admin_views')
        self.assertNotContains(response, 'Articles')
        self.client.get(reverse('admin7:logout'))


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewsNoUrlTest(TestCase):
    """Regression test for #17333"""

    fixtures = ['admin-views-users.xml']

    def setUp(self):
        opts = Report._meta
        # User who can change Reports
        change_user = User.objects.get(username='changeuser')
        change_user.user_permissions.add(get_perm(Report,
            get_permission_codename('change', opts)))

        # login POST dict
        self.changeuser_login = {
            REDIRECT_FIELD_NAME: reverse('admin:index'),
            'username': 'changeuser',
            'password': 'secret',
        }

    def test_no_standard_modeladmin_urls(self):
        """Admin index views don't break when user's ModelAdmin removes standard urls"""
        self.client.get(reverse('admin:index'))
        r = self.client.post(reverse('admin:login'), self.changeuser_login)
        r = self.client.get(reverse('admin:index'))
        # we shouldn't get a 500 error caused by a NoReverseMatch
        self.assertEqual(r.status_code, 200)
        self.client.get(reverse('admin:logout'))


@skipUnlessDBFeature('can_defer_constraint_checks')
@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewDeletedObjectsTest(TestCase):
    fixtures = ['admin-views-users.xml', 'deleted-objects.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_nesting(self):
        """
        Objects should be nested to display the relationships that
        cause them to be scheduled for deletion.
        """
        pattern = re.compile(force_bytes(
            r'<li>Plot: <a href="%s">World Domination</a>\s*<ul>\s*<li>Plot details: <a href="%s">almost finished</a>' % (
                reverse('admin:admin_views_plot_change', args=(1,)),
                reverse('admin:admin_views_plotdetails_change', args=(1,)))
        ))
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(1,)))
        six.assertRegex(self, response.content, pattern)

    def test_cyclic(self):
        """
        Cyclic relationships should still cause each object to only be
        listed once.

        """
        one = '<li>Cyclic one: <a href="%s">I am recursive</a>' % (
            reverse('admin:admin_views_cyclicone_change', args=(1,)),
        )
        two = '<li>Cyclic two: <a href="%s">I am recursive too</a>' % (
            reverse('admin:admin_views_cyclictwo_change', args=(1,)),
        )
        response = self.client.get(reverse('admin:admin_views_cyclicone_delete', args=(1,)))

        self.assertContains(response, one, 1)
        self.assertContains(response, two, 1)

    def test_perms_needed(self):
        self.client.logout()
        delete_user = User.objects.get(username='deleteuser')
        delete_user.user_permissions.add(get_perm(Plot,
            get_permission_codename('delete', Plot._meta)))

        self.assertTrue(self.client.login(username='deleteuser',
                                          password='secret'))

        response = self.client.get(reverse('admin:admin_views_plot_delete', args=(1,)))
        self.assertContains(response, "your account doesn't have permission to delete the following types of objects")
        self.assertContains(response, "<li>plot details</li>")

    def test_protected(self):
        q = Question.objects.create(question="Why?")
        a1 = Answer.objects.create(question=q, answer="Because.")
        a2 = Answer.objects.create(question=q, answer="Yes.")

        response = self.client.get(reverse('admin:admin_views_question_delete', args=(q.pk,)))
        self.assertContains(response, "would require deleting the following protected related objects")
        self.assertContains(
            response,
            '<li>Answer: <a href="%s">Because.</a></li>' % reverse('admin:admin_views_answer_change', args=(a1.pk,))
        )
        self.assertContains(
            response,
            '<li>Answer: <a href="%s">Yes.</a></li>' % reverse('admin:admin_views_answer_change', args=(a2.pk,))
        )

    def test_not_registered(self):
        should_contain = """<li>Secret hideout: underground bunker"""
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(1,)))
        self.assertContains(response, should_contain, 1)

    def test_multiple_fkeys_to_same_model(self):
        """
        If a deleted object has two relationships from another model,
        both of those should be followed in looking for related
        objects to delete.

        """
        should_contain = '<li>Plot: <a href="%s">World Domination</a>' % reverse(
            'admin:admin_views_plot_change', args=(1,)
        )
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(1,)))
        self.assertContains(response, should_contain)
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(2,)))
        self.assertContains(response, should_contain)

    def test_multiple_fkeys_to_same_instance(self):
        """
        If a deleted object has two relationships pointing to it from
        another object, the other object should still only be listed
        once.

        """
        should_contain = '<li>Plot: <a href="%s">World Peace</a></li>' % reverse(
            'admin:admin_views_plot_change', args=(2,)
        )
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(2,)))
        self.assertContains(response, should_contain, 1)

    def test_inheritance(self):
        """
        In the case of an inherited model, if either the child or
        parent-model instance is deleted, both instances are listed
        for deletion, as well as any relationships they have.

        """
        should_contain = [
            '<li>Villain: <a href="%s">Bob</a>' % reverse('admin:admin_views_villain_change', args=(3,)),
            '<li>Super villain: <a href="%s">Bob</a>' % reverse('admin:admin_views_supervillain_change', args=(3,)),
            '<li>Secret hideout: floating castle',
            '<li>Super secret hideout: super floating castle!',
        ]
        response = self.client.get(reverse('admin:admin_views_villain_delete', args=(3,)))
        for should in should_contain:
            self.assertContains(response, should, 1)
        response = self.client.get(reverse('admin:admin_views_supervillain_delete', args=(3,)))
        for should in should_contain:
            self.assertContains(response, should, 1)

    def test_generic_relations(self):
        """
        If a deleted object has GenericForeignKeys pointing to it,
        those objects should be listed for deletion.

        """
        plot = Plot.objects.get(pk=3)
        tag = FunkyTag.objects.create(content_object=plot, name='hott')
        should_contain = '<li>Funky tag: <a href="%s">hott' % reverse(
            'admin:admin_views_funkytag_change', args=(tag.id,))
        response = self.client.get(reverse('admin:admin_views_plot_delete', args=(3,)))
        self.assertContains(response, should_contain)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class TestGenericRelations(TestCase):
    fixtures = ['admin-views-users.xml', 'deleted-objects.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_generic_content_object_in_list_display(self):
        plot = Plot.objects.get(pk=3)
        FunkyTag.objects.create(content_object=plot, name='hott')
        response = self.client.get(reverse('admin:admin_views_funkytag_changelist'))
        self.assertContains(response, "%s</td>" % plot)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewStringPrimaryKeyTest(TestCase):
    fixtures = ['admin-views-users.xml', 'string-primary-key.xml']

    def __init__(self, *args):
        super(AdminViewStringPrimaryKeyTest, self).__init__(*args)
        self.pk = """abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ 1234567890 -_.!~*'() ;/?:@&=+$, <>#%" {}|\^[]`"""

    def setUp(self):
        self.client.login(username='super', password='secret')
        content_type_pk = ContentType.objects.get_for_model(ModelWithStringPrimaryKey).pk
        LogEntry.objects.log_action(100, content_type_pk, self.pk, self.pk, 2, change_message='Changed something')

    def test_get_history_view(self):
        """
        Retrieving the history for an object using urlencoded form of primary
        key should work.
        Refs #12349, #18550.
        """
        response = self.client.get(reverse('admin:admin_views_modelwithstringprimarykey_history', args=(self.pk,)))
        self.assertContains(response, escape(self.pk))
        self.assertContains(response, 'Changed something')
        self.assertEqual(response.status_code, 200)

    def test_get_change_view(self):
        "Retrieving the object using urlencoded form of primary key should work"
        response = self.client.get(reverse('admin:admin_views_modelwithstringprimarykey_change', args=(self.pk,)))
        self.assertContains(response, escape(self.pk))
        self.assertEqual(response.status_code, 200)

    def test_changelist_to_changeform_link(self):
        "Link to the changeform of the object in changelist should use reverse() and be quoted -- #18072"
        response = self.client.get(reverse('admin:admin_views_modelwithstringprimarykey_changelist'))
        # this URL now comes through reverse(), thus url quoting and iri_to_uri encoding
        pk_final_url = escape(iri_to_uri(quote(self.pk)))
        change_url = reverse(
            'admin:admin_views_modelwithstringprimarykey_change', args=('__fk__',)
        ).replace('__fk__', pk_final_url)
        should_contain = '<th class="field-__str__"><a href="%s">%s</a></th>' % (change_url, escape(self.pk))
        self.assertContains(response, should_contain)

    def test_recentactions_link(self):
        "The link from the recent actions list referring to the changeform of the object should be quoted"
        response = self.client.get(reverse('admin:index'))
        link = reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(self.pk),))
        should_contain = """<a href="%s">%s</a>""" % (escape(link), escape(self.pk))
        self.assertContains(response, should_contain)

    def test_recentactions_without_content_type(self):
        "If a LogEntry is missing content_type it will not display it in span tag under the hyperlink."
        response = self.client.get(reverse('admin:index'))
        link = reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(self.pk),))
        should_contain = """<a href="%s">%s</a>""" % (escape(link), escape(self.pk))
        self.assertContains(response, should_contain)
        should_contain = "Model with string primary key"  # capitalized in Recent Actions
        self.assertContains(response, should_contain)
        logentry = LogEntry.objects.get(content_type__model__iexact='modelwithstringprimarykey')
        # http://code.djangoproject.com/ticket/10275
        # if the log entry doesn't have a content type it should still be
        # possible to view the Recent Actions part
        logentry.content_type = None
        logentry.save()

        counted_presence_before = response.content.count(force_bytes(should_contain))
        response = self.client.get(reverse('admin:index'))
        counted_presence_after = response.content.count(force_bytes(should_contain))
        self.assertEqual(counted_presence_before - 1,
            counted_presence_after)

    def test_logentry_get_admin_url(self):
        "LogEntry.get_admin_url returns a URL to edit the entry's object or None for non-existent (possibly deleted) models"
        log_entry_model = "modelwithstringprimarykey"  # capitalized in Recent Actions
        logentry = LogEntry.objects.get(content_type__model__iexact=log_entry_model)
        desired_admin_url = reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(self.pk),))

        self.assertEqual(logentry.get_admin_url(), desired_admin_url)
        self.assertIn(iri_to_uri(quote(self.pk)), logentry.get_admin_url())

        logentry.content_type.model = "non-existent"
        self.assertEqual(logentry.get_admin_url(), None)

    def test_deleteconfirmation_link(self):
        "The link from the delete confirmation page referring back to the changeform of the object should be quoted"
        response = self.client.get(reverse('admin:admin_views_modelwithstringprimarykey_delete', args=(quote(self.pk),)))
        # this URL now comes through reverse(), thus url quoting and iri_to_uri encoding
        change_url = reverse(
            'admin:admin_views_modelwithstringprimarykey_change', args=('__fk__',)
        ).replace('__fk__', escape(iri_to_uri(quote(self.pk))))
        should_contain = '<a href="%s">%s</a>' % (change_url, escape(self.pk))
        self.assertContains(response, should_contain)

    def test_url_conflicts_with_add(self):
        "A model with a primary key that ends with add should be visible"
        add_model = ModelWithStringPrimaryKey(pk="i have something to add")
        add_model.save()
        response = self.client.get(
            reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(add_model.pk),))
        )
        should_contain = """<h1>Change model with string primary key</h1>"""
        self.assertContains(response, should_contain)

    def test_url_conflicts_with_delete(self):
        "A model with a primary key that ends with delete should be visible"
        delete_model = ModelWithStringPrimaryKey(pk="delete")
        delete_model.save()
        response = self.client.get(
            reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(delete_model.pk),))
        )
        should_contain = """<h1>Change model with string primary key</h1>"""
        self.assertContains(response, should_contain)

    def test_url_conflicts_with_history(self):
        "A model with a primary key that ends with history should be visible"
        history_model = ModelWithStringPrimaryKey(pk="history")
        history_model.save()
        response = self.client.get(
            reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(history_model.pk),))
        )
        should_contain = """<h1>Change model with string primary key</h1>"""
        self.assertContains(response, should_contain)

    def test_shortcut_view_with_escaping(self):
        "'View on site should' work properly with char fields"
        model = ModelWithStringPrimaryKey(pk='abc_123')
        model.save()
        response = self.client.get(
            reverse('admin:admin_views_modelwithstringprimarykey_change', args=(quote(model.pk),))
        )
        should_contain = '/%s/" class="viewsitelink">' % model.pk
        self.assertContains(response, should_contain)

    def test_change_view_history_link(self):
        """Object history button link should work and contain the pk value quoted."""
        url = reverse('admin:%s_modelwithstringprimarykey_change' %
            ModelWithStringPrimaryKey._meta.app_label,
            args=(quote(self.pk),))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        expected_link = reverse('admin:%s_modelwithstringprimarykey_history' %
            ModelWithStringPrimaryKey._meta.app_label,
            args=(quote(self.pk),))
        self.assertContains(response, '<a href="%s" class="historylink"' % expected_link)

    def test_redirect_on_add_view_continue_button(self):
        """As soon as an object is added using "Save and continue editing"
        button, the user should be redirected to the object's change_view.

        In case primary key is a string containing some special characters
        like slash or underscore, these characters must be escaped (see #22266)
        """
        response = self.client.post(
            reverse('admin:admin_views_modelwithstringprimarykey_add'),
            {
                'string_pk': '123/history',
                "_continue": "1",  # Save and continue editing
            }
        )

        self.assertEqual(response.status_code, 302)  # temporary redirect
        self.assertIn('/123_2Fhistory/', response['location'])  # PK is quoted


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class SecureViewTests(TestCase):
    """
    Test behavior of a view protected by the staff_member_required decorator.
    """
    fixtures = ['admin-views-users.xml']

    def test_secure_view_shows_login_if_not_logged_in(self):
        """
        Ensure that we see the admin login form.
        """
        secure_url = reverse('secure_view')
        response = self.client.get(secure_url)
        self.assertRedirects(response, '%s?next=%s' % (reverse('admin:login'), secure_url))
        response = self.client.get(secure_url, follow=True)
        self.assertTemplateUsed(response, 'admin/login.html')
        self.assertEqual(response.context[REDIRECT_FIELD_NAME], secure_url)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewUnicodeTest(TestCase):
    fixtures = ['admin-views-unicode.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_unicode_edit(self):
        """
        A test to ensure that POST on edit_view handles non-ASCII characters.
        """
        post_data = {
            "name": "Test lærdommer",
            # inline data
            "chapter_set-TOTAL_FORMS": "6",
            "chapter_set-INITIAL_FORMS": "3",
            "chapter_set-MAX_NUM_FORMS": "0",
            "chapter_set-0-id": "1",
            "chapter_set-0-title": "Norske bostaver æøå skaper problemer",
            "chapter_set-0-content": "&lt;p&gt;Svært frustrerende med UnicodeDecodeError&lt;/p&gt;",
            "chapter_set-1-id": "2",
            "chapter_set-1-title": "Kjærlighet.",
            "chapter_set-1-content": "&lt;p&gt;La kjærligheten til de lidende seire.&lt;/p&gt;",
            "chapter_set-2-id": "3",
            "chapter_set-2-title": "Need a title.",
            "chapter_set-2-content": "&lt;p&gt;Newest content&lt;/p&gt;",
            "chapter_set-3-id": "",
            "chapter_set-3-title": "",
            "chapter_set-3-content": "",
            "chapter_set-4-id": "",
            "chapter_set-4-title": "",
            "chapter_set-4-content": "",
            "chapter_set-5-id": "",
            "chapter_set-5-title": "",
            "chapter_set-5-content": "",
        }

        response = self.client.post(reverse('admin:admin_views_book_change', args=(1,)), post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere

    def test_unicode_delete(self):
        """
        Ensure that the delete_view handles non-ASCII characters
        """
        delete_dict = {'post': 'yes'}
        delete_url = reverse('admin:admin_views_book_delete', args=(1,))
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(delete_url, delete_dict)
        self.assertRedirects(response, reverse('admin:admin_views_book_changelist'))


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewListEditable(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-person.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_inheritance(self):
        Podcast.objects.create(name="This Week in Django",
            release_date=datetime.date.today())
        response = self.client.get(reverse('admin:admin_views_podcast_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_inheritance_2(self):
        Vodcast.objects.create(name="This Week in Django", released=True)
        response = self.client.get(reverse('admin:admin_views_vodcast_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_custom_pk(self):
        Language.objects.create(iso='en', name='English', english_name='English')
        response = self.client.get(reverse('admin:admin_views_language_changelist'))
        self.assertEqual(response.status_code, 200)

    def test_changelist_input_html(self):
        response = self.client.get(reverse('admin:admin_views_person_changelist'))
        # 2 inputs per object(the field and the hidden id field) = 6
        # 4 management hidden fields = 4
        # 4 action inputs (3 regular checkboxes, 1 checkbox to select all)
        # main form submit button = 1
        # search field and search submit button = 2
        # CSRF field = 1
        # field to track 'select all' across paginated views = 1
        # 6 + 4 + 4 + 1 + 2 + 1 + 1 = 19 inputs
        self.assertContains(response, "<input", count=19)
        # 1 select per object = 3 selects
        self.assertContains(response, "<select", count=4)

    def test_post_messages(self):
        # Ticket 12707: Saving inline editable should not show admin
        # action warnings
        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-gender": "1",
            "form-0-id": "1",

            "form-1-gender": "2",
            "form-1-id": "2",

            "form-2-alive": "checked",
            "form-2-gender": "1",
            "form-2-id": "3",

            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_person_changelist'),
                                    data, follow=True)
        self.assertEqual(len(response.context['messages']), 1)

    def test_post_submission(self):
        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-gender": "1",
            "form-0-id": "1",

            "form-1-gender": "2",
            "form-1-id": "2",

            "form-2-alive": "checked",
            "form-2-gender": "1",
            "form-2-id": "3",

            "_save": "Save",
        }
        self.client.post(reverse('admin:admin_views_person_changelist'), data)

        self.assertEqual(Person.objects.get(name="John Mauchly").alive, False)
        self.assertEqual(Person.objects.get(name="Grace Hopper").gender, 2)

        # test a filtered page
        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "2",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": "1",
            "form-0-gender": "1",
            "form-0-alive": "checked",

            "form-1-id": "3",
            "form-1-gender": "1",
            "form-1-alive": "checked",

            "_save": "Save",
        }
        self.client.post(reverse('admin:admin_views_person_changelist') + '?gender__exact=1', data)

        self.assertEqual(Person.objects.get(name="John Mauchly").alive, True)

        # test a searched page
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": "1",
            "form-0-gender": "1",

            "_save": "Save",
        }
        self.client.post(reverse('admin:admin_views_person_changelist') + '?q=john', data)

        self.assertEqual(Person.objects.get(name="John Mauchly").alive, False)

    def test_non_field_errors(self):
        ''' Ensure that non field errors are displayed for each of the
            forms in the changelist's formset. Refs #13126.
        '''
        fd1 = FoodDelivery.objects.create(reference='123', driver='bill', restaurant='thai')
        fd2 = FoodDelivery.objects.create(reference='456', driver='bill', restaurant='india')
        fd3 = FoodDelivery.objects.create(reference='789', driver='bill', restaurant='pizza')

        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": str(fd1.id),
            "form-0-reference": "123",
            "form-0-driver": "bill",
            "form-0-restaurant": "thai",

            # Same data as above: Forbidden because of unique_together!
            "form-1-id": str(fd2.id),
            "form-1-reference": "456",
            "form-1-driver": "bill",
            "form-1-restaurant": "thai",

            "form-2-id": str(fd3.id),
            "form-2-reference": "789",
            "form-2-driver": "bill",
            "form-2-restaurant": "pizza",

            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_fooddelivery_changelist'), data)
        self.assertContains(
            response,
            '<tr><td colspan="4"><ul class="errorlist nonfield"><li>Food delivery '
            'with this Driver and Restaurant already exists.</li></ul></td></tr>',
            1,
            html=True
        )

        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": str(fd1.id),
            "form-0-reference": "123",
            "form-0-driver": "bill",
            "form-0-restaurant": "thai",

            # Same data as above: Forbidden because of unique_together!
            "form-1-id": str(fd2.id),
            "form-1-reference": "456",
            "form-1-driver": "bill",
            "form-1-restaurant": "thai",

            # Same data also.
            "form-2-id": str(fd3.id),
            "form-2-reference": "789",
            "form-2-driver": "bill",
            "form-2-restaurant": "thai",

            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_fooddelivery_changelist'), data)
        self.assertContains(
            response,
            '<tr><td colspan="4"><ul class="errorlist nonfield"><li>Food delivery '
            'with this Driver and Restaurant already exists.</li></ul></td></tr>',
            2,
            html=True
        )

    def test_non_form_errors(self):
        # test if non-form errors are handled; ticket #12716
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": "2",
            "form-0-alive": "1",
            "form-0-gender": "2",

            # Ensure that the form processing understands this as a list_editable "Save"
            # and not an action "Go".
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_person_changelist'), data)
        self.assertContains(response, "Grace is not a Zombie")

    def test_non_form_errors_is_errorlist(self):
        # test if non-form errors are correctly handled; ticket #12878
        data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MAX_NUM_FORMS": "0",

            "form-0-id": "2",
            "form-0-alive": "1",
            "form-0-gender": "2",

            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_person_changelist'), data)
        non_form_errors = response.context['cl'].formset.non_form_errors()
        self.assertIsInstance(non_form_errors, ErrorList)
        self.assertEqual(str(non_form_errors), str(ErrorList(["Grace is not a Zombie"])))

    def test_list_editable_ordering(self):
        collector = Collector.objects.create(id=1, name="Frederick Clegg")

        Category.objects.create(id=1, order=1, collector=collector)
        Category.objects.create(id=2, order=2, collector=collector)
        Category.objects.create(id=3, order=0, collector=collector)
        Category.objects.create(id=4, order=0, collector=collector)

        # NB: The order values must be changed so that the items are reordered.
        data = {
            "form-TOTAL_FORMS": "4",
            "form-INITIAL_FORMS": "4",
            "form-MAX_NUM_FORMS": "0",

            "form-0-order": "14",
            "form-0-id": "1",
            "form-0-collector": "1",

            "form-1-order": "13",
            "form-1-id": "2",
            "form-1-collector": "1",

            "form-2-order": "1",
            "form-2-id": "3",
            "form-2-collector": "1",

            "form-3-order": "0",
            "form-3-id": "4",
            "form-3-collector": "1",

            # Ensure that the form processing understands this as a list_editable "Save"
            # and not an action "Go".
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_category_changelist'), data)
        # Successful post will redirect
        self.assertEqual(response.status_code, 302)

        # Check that the order values have been applied to the right objects
        self.assertEqual(Category.objects.get(id=1).order, 14)
        self.assertEqual(Category.objects.get(id=2).order, 13)
        self.assertEqual(Category.objects.get(id=3).order, 1)
        self.assertEqual(Category.objects.get(id=4).order, 0)

    def test_list_editable_pagination(self):
        """
        Ensure that pagination works for list_editable items.
        Refs #16819.
        """
        UnorderedObject.objects.create(id=1, name='Unordered object #1')
        UnorderedObject.objects.create(id=2, name='Unordered object #2')
        UnorderedObject.objects.create(id=3, name='Unordered object #3')
        response = self.client.get(reverse('admin:admin_views_unorderedobject_changelist'))
        self.assertContains(response, 'Unordered object #3')
        self.assertContains(response, 'Unordered object #2')
        self.assertNotContains(response, 'Unordered object #1')
        response = self.client.get(reverse('admin:admin_views_unorderedobject_changelist') + '?p=1')
        self.assertNotContains(response, 'Unordered object #3')
        self.assertNotContains(response, 'Unordered object #2')
        self.assertContains(response, 'Unordered object #1')

    def test_list_editable_action_submit(self):
        # List editable changes should not be executed if the action "Go" button is
        # used to submit the form.
        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-gender": "1",
            "form-0-id": "1",

            "form-1-gender": "2",
            "form-1-id": "2",

            "form-2-alive": "checked",
            "form-2-gender": "1",
            "form-2-id": "3",

            "index": "0",
            "_selected_action": ['3'],
            "action": ['', 'delete_selected'],
        }
        self.client.post(reverse('admin:admin_views_person_changelist'), data)

        self.assertEqual(Person.objects.get(name="John Mauchly").alive, True)
        self.assertEqual(Person.objects.get(name="Grace Hopper").gender, 1)

    def test_list_editable_action_choices(self):
        # List editable changes should be executed if the "Save" button is
        # used to submit the form - any action choices should be ignored.
        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MAX_NUM_FORMS": "0",

            "form-0-gender": "1",
            "form-0-id": "1",

            "form-1-gender": "2",
            "form-1-id": "2",

            "form-2-alive": "checked",
            "form-2-gender": "1",
            "form-2-id": "3",

            "_save": "Save",
            "_selected_action": ['1'],
            "action": ['', 'delete_selected'],
        }
        self.client.post(reverse('admin:admin_views_person_changelist'), data)

        self.assertEqual(Person.objects.get(name="John Mauchly").alive, False)
        self.assertEqual(Person.objects.get(name="Grace Hopper").gender, 2)

    def test_list_editable_popup(self):
        """
        Fields should not be list-editable in popups.
        """
        response = self.client.get(reverse('admin:admin_views_person_changelist'))
        self.assertNotEqual(response.context['cl'].list_editable, ())
        response = self.client.get(reverse('admin:admin_views_person_changelist') + '?%s' % IS_POPUP_VAR)
        self.assertEqual(response.context['cl'].list_editable, ())

    def test_pk_hidden_fields(self):
        """ Ensure that hidden pk fields aren't displayed in the table body and
            that their corresponding human-readable value is displayed instead.
            Note that the hidden pk fields are in fact be displayed but
            separately (not in the table), and only once.
            Refs #12475.
        """
        story1 = Story.objects.create(title='The adventures of Guido', content='Once upon a time in Djangoland...')
        story2 = Story.objects.create(title='Crouching Tiger, Hidden Python', content='The Python was sneaking into...')
        response = self.client.get(reverse('admin:admin_views_story_changelist'))
        self.assertContains(response, 'id="id_form-0-id"', 1)  # Only one hidden field, in a separate place than the table.
        self.assertContains(response, 'id="id_form-1-id"', 1)
        self.assertContains(response, '<div class="hiddenfields">\n<input type="hidden" name="form-0-id" value="%d" id="id_form-0-id" /><input type="hidden" name="form-1-id" value="%d" id="id_form-1-id" />\n</div>' % (story2.id, story1.id), html=True)
        self.assertContains(response, '<td class="field-id">%d</td>' % story1.id, 1)
        self.assertContains(response, '<td class="field-id">%d</td>' % story2.id, 1)

    def test_pk_hidden_fields_with_list_display_links(self):
        """ Similarly as test_pk_hidden_fields, but when the hidden pk fields are
            referenced in list_display_links.
            Refs #12475.
        """
        story1 = OtherStory.objects.create(title='The adventures of Guido', content='Once upon a time in Djangoland...')
        story2 = OtherStory.objects.create(title='Crouching Tiger, Hidden Python', content='The Python was sneaking into...')
        link1 = reverse('admin:admin_views_otherstory_change', args=(story1.pk,))
        link2 = reverse('admin:admin_views_otherstory_change', args=(story2.pk,))
        response = self.client.get(reverse('admin:admin_views_otherstory_changelist'))
        self.assertContains(response, 'id="id_form-0-id"', 1)  # Only one hidden field, in a separate place than the table.
        self.assertContains(response, 'id="id_form-1-id"', 1)
        self.assertContains(response, '<div class="hiddenfields">\n<input type="hidden" name="form-0-id" value="%d" id="id_form-0-id" /><input type="hidden" name="form-1-id" value="%d" id="id_form-1-id" />\n</div>' % (story2.id, story1.id), html=True)
        self.assertContains(response, '<th class="field-id"><a href="%s">%d</a></th>' % (link1, story1.id), 1)
        self.assertContains(response, '<th class="field-id"><a href="%s">%d</a></th>' % (link2, story2.id), 1)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminSearchTest(TestCase):
    fixtures = ['admin-views-users', 'multiple-child-classes',
                'admin-views-person']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_search_on_sibling_models(self):
        "Check that a search that mentions sibling models"
        response = self.client.get(reverse('admin:admin_views_recommendation_changelist') + '?q=bar')
        # confirm the search returned 1 object
        self.assertContains(response, "\n1 recommendation\n")

    def test_with_fk_to_field(self):
        """
        Ensure that the to_field GET parameter is preserved when a search
        is performed. Refs #10918.
        """
        response = self.client.get(reverse('admin:auth_user_changelist') + '?q=joe&%s=id' % TO_FIELD_VAR)
        self.assertContains(response, "\n1 user\n")
        self.assertContains(response, '<input type="hidden" name="%s" value="id"/>' % TO_FIELD_VAR, html=True)

    def test_exact_matches(self):
        response = self.client.get(reverse('admin:admin_views_recommendation_changelist') + '?q=bar')
        # confirm the search returned one object
        self.assertContains(response, "\n1 recommendation\n")

        response = self.client.get(reverse('admin:admin_views_recommendation_changelist') + '?q=ba')
        # confirm the search returned zero objects
        self.assertContains(response, "\n0 recommendations\n")

    def test_beginning_matches(self):
        response = self.client.get(reverse('admin:admin_views_person_changelist') + '?q=Gui')
        # confirm the search returned one object
        self.assertContains(response, "\n1 person\n")
        self.assertContains(response, "Guido")

        response = self.client.get(reverse('admin:admin_views_person_changelist') + '?q=uido')
        # confirm the search returned zero objects
        self.assertContains(response, "\n0 persons\n")
        self.assertNotContains(response, "Guido")

    def test_pluggable_search(self):
        PluggableSearchPerson.objects.create(name="Bob", age=10)
        PluggableSearchPerson.objects.create(name="Amy", age=20)

        response = self.client.get(reverse('admin:admin_views_pluggablesearchperson_changelist') + '?q=Bob')
        # confirm the search returned one object
        self.assertContains(response, "\n1 pluggable search person\n")
        self.assertContains(response, "Bob")

        response = self.client.get(reverse('admin:admin_views_pluggablesearchperson_changelist') + '?q=20')
        # confirm the search returned one object
        self.assertContains(response, "\n1 pluggable search person\n")
        self.assertContains(response, "Amy")

    def test_reset_link(self):
        """
        Test presence of reset link in search bar ("1 result (_x total_)").
        """
        #   1 query for session + 1 for fetching user
        # + 1 for filtered result + 1 for filtered count
        # + 1 for total count
        with self.assertNumQueries(5):
            response = self.client.get(reverse('admin:admin_views_person_changelist') + '?q=Gui')
        self.assertContains(response,
            """<span class="small quiet">1 result (<a href="?">3 total</a>)</span>""",
            html=True)

    def test_no_total_count(self):
        """
        #8408 -- "Show all" should be displayed instead of the total count if
        ModelAdmin.show_full_result_count is False.
        """
        #   1 query for session + 1 for fetching user
        # + 1 for filtered result + 1 for filtered count
        with self.assertNumQueries(4):
            response = self.client.get(reverse('admin:admin_views_recommendation_changelist') + '?q=bar')
        self.assertContains(response,
            """<span class="small quiet">1 result (<a href="?">Show all</a>)</span>""",
            html=True)
        self.assertTrue(response.context['cl'].show_admin_actions)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminInheritedInlinesTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_inline(self):
        "Ensure that inline models which inherit from a common parent are correctly handled by admin."

        foo_user = "foo username"
        bar_user = "bar username"

        name_re = re.compile(b'name="(.*?)"')

        # test the add case
        response = self.client.get(reverse('admin:admin_views_persona_add'))
        names = name_re.findall(response.content)
        # make sure we have no duplicate HTML names
        self.assertEqual(len(names), len(set(names)))

        # test the add case
        post_data = {
            "name": "Test Name",
            # inline data
            "accounts-TOTAL_FORMS": "1",
            "accounts-INITIAL_FORMS": "0",
            "accounts-MAX_NUM_FORMS": "0",
            "accounts-0-username": foo_user,
            "accounts-2-TOTAL_FORMS": "1",
            "accounts-2-INITIAL_FORMS": "0",
            "accounts-2-MAX_NUM_FORMS": "0",
            "accounts-2-0-username": bar_user,
        }

        response = self.client.post(reverse('admin:admin_views_persona_add'), post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere
        self.assertEqual(Persona.objects.count(), 1)
        self.assertEqual(FooAccount.objects.count(), 1)
        self.assertEqual(BarAccount.objects.count(), 1)
        self.assertEqual(FooAccount.objects.all()[0].username, foo_user)
        self.assertEqual(BarAccount.objects.all()[0].username, bar_user)
        self.assertEqual(Persona.objects.all()[0].accounts.count(), 2)

        persona_id = Persona.objects.all()[0].id
        foo_id = FooAccount.objects.all()[0].id
        bar_id = BarAccount.objects.all()[0].id

        # test the edit case

        response = self.client.get(reverse('admin:admin_views_persona_change', args=(persona_id,)))
        names = name_re.findall(response.content)
        # make sure we have no duplicate HTML names
        self.assertEqual(len(names), len(set(names)))

        post_data = {
            "name": "Test Name",

            "accounts-TOTAL_FORMS": "2",
            "accounts-INITIAL_FORMS": "1",
            "accounts-MAX_NUM_FORMS": "0",

            "accounts-0-username": "%s-1" % foo_user,
            "accounts-0-account_ptr": str(foo_id),
            "accounts-0-persona": str(persona_id),

            "accounts-2-TOTAL_FORMS": "2",
            "accounts-2-INITIAL_FORMS": "1",
            "accounts-2-MAX_NUM_FORMS": "0",

            "accounts-2-0-username": "%s-1" % bar_user,
            "accounts-2-0-account_ptr": str(bar_id),
            "accounts-2-0-persona": str(persona_id),
        }
        response = self.client.post(reverse('admin:admin_views_persona_change', args=(persona_id,)), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Persona.objects.count(), 1)
        self.assertEqual(FooAccount.objects.count(), 1)
        self.assertEqual(BarAccount.objects.count(), 1)
        self.assertEqual(FooAccount.objects.all()[0].username, "%s-1" % foo_user)
        self.assertEqual(BarAccount.objects.all()[0].username, "%s-1" % bar_user)
        self.assertEqual(Persona.objects.all()[0].accounts.count(), 2)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminActionsTest(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-actions.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_model_admin_custom_action(self):
        "Tests a custom action defined in a ModelAdmin method"
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'mail_admin',
            'index': 0,
        }
        self.client.post(reverse('admin:admin_views_subscriber_changelist'), action_data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Greetings from a ModelAdmin action')

    def test_model_admin_default_delete_action(self):
        "Tests the default delete action defined as a ModelAdmin method"
        action_data = {
            ACTION_CHECKBOX_NAME: [1, 2],
            'action': 'delete_selected',
            'index': 0,
        }
        delete_confirmation_data = {
            ACTION_CHECKBOX_NAME: [1, 2],
            'action': 'delete_selected',
            'post': 'yes',
        }
        confirmation = self.client.post(reverse('admin:admin_views_subscriber_changelist'), action_data)
        self.assertIsInstance(confirmation, TemplateResponse)
        self.assertContains(confirmation, "Are you sure you want to delete the selected subscribers?")
        self.assertContains(confirmation, "<h2>Summary</h2>")
        self.assertContains(confirmation, "<li>Subscribers: 3</li>")
        self.assertContains(confirmation, "<li>External subscribers: 1</li>")
        self.assertContains(confirmation, ACTION_CHECKBOX_NAME, count=2)
        self.client.post(reverse('admin:admin_views_subscriber_changelist'), delete_confirmation_data)
        self.assertEqual(Subscriber.objects.count(), 0)

    @override_settings(USE_THOUSAND_SEPARATOR=True, USE_L10N=True)
    def test_non_localized_pk(self):
        """If USE_THOUSAND_SEPARATOR is set, make sure that the ids for
        the objects selected for deletion are rendered without separators.
        Refs #14895.
        """
        subscriber = Subscriber.objects.get(id=1)
        subscriber.id = 9999
        subscriber.save()
        action_data = {
            ACTION_CHECKBOX_NAME: [9999, 2],
            'action': 'delete_selected',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_subscriber_changelist'), action_data)
        self.assertTemplateUsed(response, 'admin/delete_selected_confirmation.html')
        self.assertContains(response, 'value="9999"')  # Instead of 9,999
        self.assertContains(response, 'value="2"')

    def test_model_admin_default_delete_action_protected(self):
        """
        Tests the default delete action defined as a ModelAdmin method in the
        case where some related objects are protected from deletion.
        """
        q1 = Question.objects.create(question="Why?")
        a1 = Answer.objects.create(question=q1, answer="Because.")
        a2 = Answer.objects.create(question=q1, answer="Yes.")
        q2 = Question.objects.create(question="Wherefore?")

        action_data = {
            ACTION_CHECKBOX_NAME: [q1.pk, q2.pk],
            'action': 'delete_selected',
            'index': 0,
        }

        response = self.client.post(reverse('admin:admin_views_question_changelist'), action_data)

        self.assertContains(response, "would require deleting the following protected related objects")
        self.assertContains(
            response,
            '<li>Answer: <a href="%s">Because.</a></li>' % reverse('admin:admin_views_answer_change', args=(a1.pk,)),
            html=True
        )
        self.assertContains(
            response,
            '<li>Answer: <a href="%s">Yes.</a></li>' % reverse('admin:admin_views_answer_change', args=(a2.pk,)),
            html=True
        )

    def test_model_admin_default_delete_action_no_change_url(self):
        """
        Default delete action shouldn't break if a user's ModelAdmin removes the url for change_view.

        Regression test for #20640
        """
        obj = UnchangeableObject.objects.create()
        action_data = {
            ACTION_CHECKBOX_NAME: obj.pk,
            "action": "delete_selected",
            "index": "0",
        }
        response = self.client.post(reverse('admin:admin_views_unchangeableobject_changelist'), action_data)
        # No 500 caused by NoReverseMatch
        self.assertEqual(response.status_code, 200)
        # The page shouldn't display a link to the nonexistent change page
        self.assertContains(response, "<li>Unchangeable object: UnchangeableObject object</li>", 1, html=True)

    def test_custom_function_mail_action(self):
        "Tests a custom action defined in a function"
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'external_mail',
            'index': 0,
        }
        self.client.post(reverse('admin:admin_views_externalsubscriber_changelist'), action_data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Greetings from a function action')

    def test_custom_function_action_with_redirect(self):
        "Tests a custom action defined in a function"
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'redirect_to',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_externalsubscriber_changelist'), action_data)
        self.assertEqual(response.status_code, 302)

    def test_default_redirect(self):
        """
        Test that actions which don't return an HttpResponse are redirected to
        the same page, retaining the querystring (which may contain changelist
        information).
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'external_mail',
            'index': 0,
        }
        url = reverse('admin:admin_views_externalsubscriber_changelist') + '?o=1'
        response = self.client.post(url, action_data)
        self.assertRedirects(response, url)

    def test_custom_function_action_streaming_response(self):
        """Tests a custom action that returns a StreamingHttpResponse."""
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'download',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_externalsubscriber_changelist'), action_data)
        content = b''.join(response.streaming_content)
        self.assertEqual(content, b'This is the content of the file')
        self.assertEqual(response.status_code, 200)

    def test_custom_function_action_no_perm_response(self):
        """Tests a custom action that returns an HttpResponse with 403 code."""
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'no_perm',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_externalsubscriber_changelist'), action_data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, b'No permission to perform this action')

    def test_actions_ordering(self):
        """
        Ensure that actions are ordered as expected.
        Refs #15964.
        """
        response = self.client.get(reverse('admin:admin_views_externalsubscriber_changelist'))
        self.assertContains(response, '''<label>Action: <select name="action">
<option value="" selected="selected">---------</option>
<option value="delete_selected">Delete selected external
subscribers</option>
<option value="redirect_to">Redirect to (Awesome action)</option>
<option value="external_mail">External mail (Another awesome
action)</option>
<option value="download">Download subscription</option>
<option value="no_perm">No permission to run</option>
</select>''', html=True)

    def test_model_without_action(self):
        "Tests a ModelAdmin without any action"
        response = self.client.get(reverse('admin:admin_views_oldsubscriber_changelist'))
        self.assertEqual(response.context["action_form"], None)
        self.assertNotContains(response, '<input type="checkbox" class="action-select"',
            msg_prefix="Found an unexpected action toggle checkboxbox in response")
        self.assertNotContains(response, '<input type="checkbox" class="action-select"')

    def test_model_without_action_still_has_jquery(self):
        "Tests that a ModelAdmin without any actions still gets jQuery included in page"
        response = self.client.get(reverse('admin:admin_views_oldsubscriber_changelist'))
        self.assertEqual(response.context["action_form"], None)
        self.assertContains(response, 'jquery.min.js',
            msg_prefix="jQuery missing from admin pages for model with no admin actions")

    def test_action_column_class(self):
        "Tests that the checkbox column class is present in the response"
        response = self.client.get(reverse('admin:admin_views_subscriber_changelist'))
        self.assertNotEqual(response.context["action_form"], None)
        self.assertContains(response, 'action-checkbox-column')

    def test_multiple_actions_form(self):
        """
        Test that actions come from the form whose submit button was pressed (#10618).
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            # Two different actions selected on the two forms...
            'action': ['external_mail', 'delete_selected'],
            # ...but we clicked "go" on the top form.
            'index': 0
        }
        self.client.post(reverse('admin:admin_views_externalsubscriber_changelist'), action_data)

        # Send mail, don't delete.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Greetings from a function action')

    def test_user_message_on_none_selected(self):
        """
        User should see a warning when 'Go' is pressed and no items are selected.
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [],
            'action': 'delete_selected',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_subscriber_changelist'), action_data)
        msg = """Items must be selected in order to perform actions on them. No items have been changed."""
        self.assertContains(response, msg)
        self.assertEqual(Subscriber.objects.count(), 2)

    def test_user_message_on_no_action(self):
        """
        User should see a warning when 'Go' is pressed and no action is selected.
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [1, 2],
            'action': '',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_subscriber_changelist'), action_data)
        msg = """No action selected."""
        self.assertContains(response, msg)
        self.assertEqual(Subscriber.objects.count(), 2)

    def test_selection_counter(self):
        """
        Check if the selection counter is there.
        """
        response = self.client.get(reverse('admin:admin_views_subscriber_changelist'))
        self.assertContains(response, '0 of 2 selected')

    def test_popup_actions(self):
        """ Actions should not be shown in popups. """
        response = self.client.get(reverse('admin:admin_views_subscriber_changelist'))
        self.assertNotEqual(response.context["action_form"], None)
        response = self.client.get(
            reverse('admin:admin_views_subscriber_changelist') + '?%s' % IS_POPUP_VAR)
        self.assertEqual(response.context["action_form"], None)

    def test_popup_template_response(self):
        """
        Success on popups shall be rendered from template in order to allow
        easy customization.
        """
        response = self.client.post(
            reverse('admin:admin_views_actor_add') + '?%s=1' % IS_POPUP_VAR,
            {'name': 'Troy McClure', 'age': '55', IS_POPUP_VAR: '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, 'admin/popup_response.html')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class TestCustomChangeList(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        result = self.client.login(username='super', password='secret')
        self.assertEqual(result, True)

    def test_custom_changelist(self):
        """
        Validate that a custom ChangeList class can be used (#9749)
        """
        # Insert some data
        post_data = {"name": "First Gadget"}
        response = self.client.post(reverse('admin:admin_views_gadget_add'), post_data)
        self.assertEqual(response.status_code, 302)  # redirect somewhere
        # Hit the page once to get messages out of the queue message list
        response = self.client.get(reverse('admin:admin_views_gadget_changelist'))
        # Ensure that data is still not visible on the page
        response = self.client.get(reverse('admin:admin_views_gadget_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'First Gadget')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class TestInlineNotEditable(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        result = self.client.login(username='super', password='secret')
        self.assertEqual(result, True)

    def test_GET_parent_add(self):
        """
        InlineModelAdmin broken?
        """
        response = self.client.get(reverse('admin:admin_views_parent_add'))
        self.assertEqual(response.status_code, 200)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminCustomQuerysetTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')
        self.pks = [EmptyModel.objects.create().id for i in range(3)]
        self.super_login = {
            REDIRECT_FIELD_NAME: reverse('admin:index'),
            'username': 'super',
            'password': 'secret',
        }

    def test_changelist_view(self):
        response = self.client.get(reverse('admin:admin_views_emptymodel_changelist'))
        for i in self.pks:
            if i > 1:
                self.assertContains(response, 'Primary key = %s' % i)
            else:
                self.assertNotContains(response, 'Primary key = %s' % i)

    def test_changelist_view_count_queries(self):
        # create 2 Person objects
        Person.objects.create(name='person1', gender=1)
        Person.objects.create(name='person2', gender=2)
        changelist_url = reverse('admin:admin_views_person_changelist')

        # 4 queries are expected: 1 for the session, 1 for the user,
        # 1 for the count and 1 for the objects on the page
        with self.assertNumQueries(4):
            resp = self.client.get(changelist_url)
            self.assertEqual(resp.context['selection_note'], '0 of 2 selected')
            self.assertEqual(resp.context['selection_note_all'], 'All 2 selected')
        # here one more count(*) query will run, because filters were applied
        with self.assertNumQueries(5):
            extra = {'q': 'not_in_name'}
            resp = self.client.get(changelist_url, extra)
            self.assertEqual(resp.context['selection_note'], '0 of 0 selected')
            self.assertEqual(resp.context['selection_note_all'], 'All 0 selected')
        with self.assertNumQueries(5):
            extra = {'q': 'person'}
            resp = self.client.get(changelist_url, extra)
            self.assertEqual(resp.context['selection_note'], '0 of 2 selected')
            self.assertEqual(resp.context['selection_note_all'], 'All 2 selected')
        with self.assertNumQueries(5):
            extra = {'gender__exact': '1'}
            resp = self.client.get(changelist_url, extra)
            self.assertEqual(resp.context['selection_note'], '0 of 1 selected')
            self.assertEqual(resp.context['selection_note_all'], '1 selected')

    def test_change_view(self):
        for i in self.pks:
            response = self.client.get(reverse('admin:admin_views_emptymodel_change', args=(i,)))
            if i > 1:
                self.assertEqual(response.status_code, 200)
            else:
                self.assertEqual(response.status_code, 404)

    def test_add_model_modeladmin_defer_qs(self):
        # Test for #14529. defer() is used in ModelAdmin.get_queryset()

        # model has __unicode__ method
        self.assertEqual(CoverLetter.objects.count(), 0)
        # Emulate model instance creation via the admin
        post_data = {
            "author": "Candidate, Best",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_coverletter_add'),
                                    post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CoverLetter.objects.count(), 1)
        # Message should contain non-ugly model verbose name
        self.assertContains(
            response,
            '<li class="success">The cover letter &quot;Candidate, Best&quot; was added successfully.</li>',
            html=True
        )

        # model has no __unicode__ method
        self.assertEqual(ShortMessage.objects.count(), 0)
        # Emulate model instance creation via the admin
        post_data = {
            "content": "What's this SMS thing?",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_shortmessage_add'),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShortMessage.objects.count(), 1)
        # Message should contain non-ugly model verbose name
        self.assertContains(
            response,
            '<li class="success">The short message &quot;ShortMessage object&quot; was added successfully.</li>',
            html=True
        )

    def test_add_model_modeladmin_only_qs(self):
        # Test for #14529. only() is used in ModelAdmin.get_queryset()

        # model has __unicode__ method
        self.assertEqual(Telegram.objects.count(), 0)
        # Emulate model instance creation via the admin
        post_data = {
            "title": "Urgent telegram",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_telegram_add'),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Telegram.objects.count(), 1)
        # Message should contain non-ugly model verbose name
        self.assertContains(
            response,
            '<li class="success">The telegram &quot;Urgent telegram&quot; was added successfully.</li>',
            html=True
        )

        # model has no __unicode__ method
        self.assertEqual(Paper.objects.count(), 0)
        # Emulate model instance creation via the admin
        post_data = {
            "title": "My Modified Paper Title",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_paper_add'),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Paper.objects.count(), 1)
        # Message should contain non-ugly model verbose name
        self.assertContains(
            response,
            '<li class="success">The paper &quot;Paper object&quot; was added successfully.</li>',
            html=True
        )

    def test_edit_model_modeladmin_defer_qs(self):
        # Test for #14529. defer() is used in ModelAdmin.get_queryset()

        # model has __unicode__ method
        cl = CoverLetter.objects.create(author="John Doe")
        self.assertEqual(CoverLetter.objects.count(), 1)
        response = self.client.get(reverse('admin:admin_views_coverletter_change', args=(cl.pk,)))
        self.assertEqual(response.status_code, 200)
        # Emulate model instance edit via the admin
        post_data = {
            "author": "John Doe II",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_coverletter_change', args=(cl.pk,)),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CoverLetter.objects.count(), 1)
        # Message should contain non-ugly model verbose name. Instance
        # representation is set by model's __unicode__()
        self.assertContains(
            response,
            '<li class="success">The cover letter &quot;John Doe II&quot; was changed successfully.</li>',
            html=True
        )

        # model has no __unicode__ method
        sm = ShortMessage.objects.create(content="This is expensive")
        self.assertEqual(ShortMessage.objects.count(), 1)
        response = self.client.get(reverse('admin:admin_views_shortmessage_change', args=(sm.pk,)))
        self.assertEqual(response.status_code, 200)
        # Emulate model instance edit via the admin
        post_data = {
            "content": "Too expensive",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_shortmessage_change', args=(sm.pk,)),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShortMessage.objects.count(), 1)
        # Message should contain non-ugly model verbose name. The ugly(!)
        # instance representation is set by six.text_type()
        self.assertContains(
            response,
            '<li class="success">The short message &quot;ShortMessage_Deferred_timestamp object&quot; was changed successfully.</li>',
            html=True
        )

    def test_edit_model_modeladmin_only_qs(self):
        # Test for #14529. only() is used in ModelAdmin.get_queryset()

        # model has __unicode__ method
        t = Telegram.objects.create(title="Frist Telegram")
        self.assertEqual(Telegram.objects.count(), 1)
        response = self.client.get(reverse('admin:admin_views_telegram_change', args=(t.pk,)))
        self.assertEqual(response.status_code, 200)
        # Emulate model instance edit via the admin
        post_data = {
            "title": "Telegram without typo",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_telegram_change', args=(t.pk,)),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Telegram.objects.count(), 1)
        # Message should contain non-ugly model verbose name. The instance
        # representation is set by model's __unicode__()
        self.assertContains(
            response,
            '<li class="success">The telegram &quot;Telegram without typo&quot; was changed successfully.</li>',
            html=True
        )

        # model has no __unicode__ method
        p = Paper.objects.create(title="My Paper Title")
        self.assertEqual(Paper.objects.count(), 1)
        response = self.client.get(reverse('admin:admin_views_paper_change', args=(p.pk,)))
        self.assertEqual(response.status_code, 200)
        # Emulate model instance edit via the admin
        post_data = {
            "title": "My Modified Paper Title",
            "_save": "Save",
        }
        response = self.client.post(reverse('admin:admin_views_paper_change', args=(p.pk,)),
                post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Paper.objects.count(), 1)
        # Message should contain non-ugly model verbose name. The ugly(!)
        # instance representation is set by six.text_type()
        self.assertContains(
            response,
            '<li class="success">The paper &quot;Paper_Deferred_author object&quot; was changed successfully.</li>',
            html=True
        )

    def test_history_view_custom_qs(self):
        """
        Ensure that custom querysets are considered for the admin history view.
        Refs #21013.
        """
        self.client.post(reverse('admin:login'), self.super_login)
        FilteredManager.objects.create(pk=1)
        FilteredManager.objects.create(pk=2)
        response = self.client.get(reverse('admin:admin_views_filteredmanager_changelist'))
        self.assertContains(response, "PK=1")
        self.assertContains(response, "PK=2")
        self.assertEqual(
            self.client.get(reverse('admin:admin_views_filteredmanager_history', args=(1,))).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse('admin:admin_views_filteredmanager_history', args=(2,))).status_code, 200
        )


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminInlineFileUploadTest(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-actions.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

        # Set up test Picture and Gallery.
        # These must be set up here instead of in fixtures in order to allow Picture
        # to use a NamedTemporaryFile.
        file1 = tempfile.NamedTemporaryFile(suffix=".file1")
        file1.write(b'a' * (2 ** 21))
        filename = file1.name
        file1.close()
        self.gallery = Gallery(name="Test Gallery")
        self.gallery.save()
        self.picture = Picture(name="Test Picture", image=filename, gallery=self.gallery)
        self.picture.save()

    def test_inline_file_upload_edit_validation_error_post(self):
        """
        Test that inline file uploads correctly display prior data (#10002).
        """
        post_data = {
            "name": "Test Gallery",
            "pictures-TOTAL_FORMS": "2",
            "pictures-INITIAL_FORMS": "1",
            "pictures-MAX_NUM_FORMS": "0",
            "pictures-0-id": six.text_type(self.picture.id),
            "pictures-0-gallery": six.text_type(self.gallery.id),
            "pictures-0-name": "Test Picture",
            "pictures-0-image": "",
            "pictures-1-id": "",
            "pictures-1-gallery": str(self.gallery.id),
            "pictures-1-name": "Test Picture 2",
            "pictures-1-image": "",
        }
        response = self.client.post(
            reverse('admin:admin_views_gallery_change', args=(self.gallery.id,)), post_data
        )
        self.assertContains(response, b"Currently")


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminInlineTests(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.post_data = {
            "name": "Test Name",

            "widget_set-TOTAL_FORMS": "3",
            "widget_set-INITIAL_FORMS": "0",
            "widget_set-MAX_NUM_FORMS": "0",
            "widget_set-0-id": "",
            "widget_set-0-owner": "1",
            "widget_set-0-name": "",
            "widget_set-1-id": "",
            "widget_set-1-owner": "1",
            "widget_set-1-name": "",
            "widget_set-2-id": "",
            "widget_set-2-owner": "1",
            "widget_set-2-name": "",

            "doohickey_set-TOTAL_FORMS": "3",
            "doohickey_set-INITIAL_FORMS": "0",
            "doohickey_set-MAX_NUM_FORMS": "0",
            "doohickey_set-0-owner": "1",
            "doohickey_set-0-code": "",
            "doohickey_set-0-name": "",
            "doohickey_set-1-owner": "1",
            "doohickey_set-1-code": "",
            "doohickey_set-1-name": "",
            "doohickey_set-2-owner": "1",
            "doohickey_set-2-code": "",
            "doohickey_set-2-name": "",

            "grommet_set-TOTAL_FORMS": "3",
            "grommet_set-INITIAL_FORMS": "0",
            "grommet_set-MAX_NUM_FORMS": "0",
            "grommet_set-0-code": "",
            "grommet_set-0-owner": "1",
            "grommet_set-0-name": "",
            "grommet_set-1-code": "",
            "grommet_set-1-owner": "1",
            "grommet_set-1-name": "",
            "grommet_set-2-code": "",
            "grommet_set-2-owner": "1",
            "grommet_set-2-name": "",

            "whatsit_set-TOTAL_FORMS": "3",
            "whatsit_set-INITIAL_FORMS": "0",
            "whatsit_set-MAX_NUM_FORMS": "0",
            "whatsit_set-0-owner": "1",
            "whatsit_set-0-index": "",
            "whatsit_set-0-name": "",
            "whatsit_set-1-owner": "1",
            "whatsit_set-1-index": "",
            "whatsit_set-1-name": "",
            "whatsit_set-2-owner": "1",
            "whatsit_set-2-index": "",
            "whatsit_set-2-name": "",

            "fancydoodad_set-TOTAL_FORMS": "3",
            "fancydoodad_set-INITIAL_FORMS": "0",
            "fancydoodad_set-MAX_NUM_FORMS": "0",
            "fancydoodad_set-0-doodad_ptr": "",
            "fancydoodad_set-0-owner": "1",
            "fancydoodad_set-0-name": "",
            "fancydoodad_set-0-expensive": "on",
            "fancydoodad_set-1-doodad_ptr": "",
            "fancydoodad_set-1-owner": "1",
            "fancydoodad_set-1-name": "",
            "fancydoodad_set-1-expensive": "on",
            "fancydoodad_set-2-doodad_ptr": "",
            "fancydoodad_set-2-owner": "1",
            "fancydoodad_set-2-name": "",
            "fancydoodad_set-2-expensive": "on",

            "category_set-TOTAL_FORMS": "3",
            "category_set-INITIAL_FORMS": "0",
            "category_set-MAX_NUM_FORMS": "0",
            "category_set-0-order": "",
            "category_set-0-id": "",
            "category_set-0-collector": "1",
            "category_set-1-order": "",
            "category_set-1-id": "",
            "category_set-1-collector": "1",
            "category_set-2-order": "",
            "category_set-2-id": "",
            "category_set-2-collector": "1",
        }

        result = self.client.login(username='super', password='secret')
        self.assertEqual(result, True)
        self.collector = Collector(pk=1, name='John Fowles')
        self.collector.save()

    def test_simple_inline(self):
        "A simple model can be saved as inlines"
        # First add a new inline
        self.post_data['widget_set-0-name'] = "Widget 1"
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Widget.objects.count(), 1)
        self.assertEqual(Widget.objects.all()[0].name, "Widget 1")
        widget_id = Widget.objects.all()[0].id

        # Check that the PK link exists on the rendered form
        response = self.client.get(collector_url)
        self.assertContains(response, 'name="widget_set-0-id"')

        # Now resave that inline
        self.post_data['widget_set-INITIAL_FORMS'] = "1"
        self.post_data['widget_set-0-id'] = str(widget_id)
        self.post_data['widget_set-0-name'] = "Widget 1"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Widget.objects.count(), 1)
        self.assertEqual(Widget.objects.all()[0].name, "Widget 1")

        # Now modify that inline
        self.post_data['widget_set-INITIAL_FORMS'] = "1"
        self.post_data['widget_set-0-id'] = str(widget_id)
        self.post_data['widget_set-0-name'] = "Widget 1 Updated"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Widget.objects.count(), 1)
        self.assertEqual(Widget.objects.all()[0].name, "Widget 1 Updated")

    def test_explicit_autofield_inline(self):
        "A model with an explicit autofield primary key can be saved as inlines. Regression for #8093"
        # First add a new inline
        self.post_data['grommet_set-0-name'] = "Grommet 1"
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Grommet.objects.count(), 1)
        self.assertEqual(Grommet.objects.all()[0].name, "Grommet 1")

        # Check that the PK link exists on the rendered form
        response = self.client.get(collector_url)
        self.assertContains(response, 'name="grommet_set-0-code"')

        # Now resave that inline
        self.post_data['grommet_set-INITIAL_FORMS'] = "1"
        self.post_data['grommet_set-0-code'] = str(Grommet.objects.all()[0].code)
        self.post_data['grommet_set-0-name'] = "Grommet 1"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Grommet.objects.count(), 1)
        self.assertEqual(Grommet.objects.all()[0].name, "Grommet 1")

        # Now modify that inline
        self.post_data['grommet_set-INITIAL_FORMS'] = "1"
        self.post_data['grommet_set-0-code'] = str(Grommet.objects.all()[0].code)
        self.post_data['grommet_set-0-name'] = "Grommet 1 Updated"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Grommet.objects.count(), 1)
        self.assertEqual(Grommet.objects.all()[0].name, "Grommet 1 Updated")

    def test_char_pk_inline(self):
        "A model with a character PK can be saved as inlines. Regression for #10992"
        # First add a new inline
        self.post_data['doohickey_set-0-code'] = "DH1"
        self.post_data['doohickey_set-0-name'] = "Doohickey 1"
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DooHickey.objects.count(), 1)
        self.assertEqual(DooHickey.objects.all()[0].name, "Doohickey 1")

        # Check that the PK link exists on the rendered form
        response = self.client.get(collector_url)
        self.assertContains(response, 'name="doohickey_set-0-code"')

        # Now resave that inline
        self.post_data['doohickey_set-INITIAL_FORMS'] = "1"
        self.post_data['doohickey_set-0-code'] = "DH1"
        self.post_data['doohickey_set-0-name'] = "Doohickey 1"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DooHickey.objects.count(), 1)
        self.assertEqual(DooHickey.objects.all()[0].name, "Doohickey 1")

        # Now modify that inline
        self.post_data['doohickey_set-INITIAL_FORMS'] = "1"
        self.post_data['doohickey_set-0-code'] = "DH1"
        self.post_data['doohickey_set-0-name'] = "Doohickey 1 Updated"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DooHickey.objects.count(), 1)
        self.assertEqual(DooHickey.objects.all()[0].name, "Doohickey 1 Updated")

    def test_integer_pk_inline(self):
        "A model with an integer PK can be saved as inlines. Regression for #10992"
        # First add a new inline
        self.post_data['whatsit_set-0-index'] = "42"
        self.post_data['whatsit_set-0-name'] = "Whatsit 1"
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Whatsit.objects.count(), 1)
        self.assertEqual(Whatsit.objects.all()[0].name, "Whatsit 1")

        # Check that the PK link exists on the rendered form
        response = self.client.get(collector_url)
        self.assertContains(response, 'name="whatsit_set-0-index"')

        # Now resave that inline
        self.post_data['whatsit_set-INITIAL_FORMS'] = "1"
        self.post_data['whatsit_set-0-index'] = "42"
        self.post_data['whatsit_set-0-name'] = "Whatsit 1"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Whatsit.objects.count(), 1)
        self.assertEqual(Whatsit.objects.all()[0].name, "Whatsit 1")

        # Now modify that inline
        self.post_data['whatsit_set-INITIAL_FORMS'] = "1"
        self.post_data['whatsit_set-0-index'] = "42"
        self.post_data['whatsit_set-0-name'] = "Whatsit 1 Updated"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Whatsit.objects.count(), 1)
        self.assertEqual(Whatsit.objects.all()[0].name, "Whatsit 1 Updated")

    def test_inherited_inline(self):
        "An inherited model can be saved as inlines. Regression for #11042"
        # First add a new inline
        self.post_data['fancydoodad_set-0-name'] = "Fancy Doodad 1"
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FancyDoodad.objects.count(), 1)
        self.assertEqual(FancyDoodad.objects.all()[0].name, "Fancy Doodad 1")
        doodad_pk = FancyDoodad.objects.all()[0].pk

        # Check that the PK link exists on the rendered form
        response = self.client.get(collector_url)
        self.assertContains(response, 'name="fancydoodad_set-0-doodad_ptr"')

        # Now resave that inline
        self.post_data['fancydoodad_set-INITIAL_FORMS'] = "1"
        self.post_data['fancydoodad_set-0-doodad_ptr'] = str(doodad_pk)
        self.post_data['fancydoodad_set-0-name'] = "Fancy Doodad 1"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FancyDoodad.objects.count(), 1)
        self.assertEqual(FancyDoodad.objects.all()[0].name, "Fancy Doodad 1")

        # Now modify that inline
        self.post_data['fancydoodad_set-INITIAL_FORMS'] = "1"
        self.post_data['fancydoodad_set-0-doodad_ptr'] = str(doodad_pk)
        self.post_data['fancydoodad_set-0-name'] = "Fancy Doodad 1 Updated"
        response = self.client.post(collector_url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FancyDoodad.objects.count(), 1)
        self.assertEqual(FancyDoodad.objects.all()[0].name, "Fancy Doodad 1 Updated")

    def test_ordered_inline(self):
        """Check that an inline with an editable ordering fields is
        updated correctly. Regression for #10922"""
        # Create some objects with an initial ordering
        Category.objects.create(id=1, order=1, collector=self.collector)
        Category.objects.create(id=2, order=2, collector=self.collector)
        Category.objects.create(id=3, order=0, collector=self.collector)
        Category.objects.create(id=4, order=0, collector=self.collector)

        # NB: The order values must be changed so that the items are reordered.
        self.post_data.update({
            "name": "Frederick Clegg",

            "category_set-TOTAL_FORMS": "7",
            "category_set-INITIAL_FORMS": "4",
            "category_set-MAX_NUM_FORMS": "0",

            "category_set-0-order": "14",
            "category_set-0-id": "1",
            "category_set-0-collector": "1",

            "category_set-1-order": "13",
            "category_set-1-id": "2",
            "category_set-1-collector": "1",

            "category_set-2-order": "1",
            "category_set-2-id": "3",
            "category_set-2-collector": "1",

            "category_set-3-order": "0",
            "category_set-3-id": "4",
            "category_set-3-collector": "1",

            "category_set-4-order": "",
            "category_set-4-id": "",
            "category_set-4-collector": "1",

            "category_set-5-order": "",
            "category_set-5-id": "",
            "category_set-5-collector": "1",

            "category_set-6-order": "",
            "category_set-6-id": "",
            "category_set-6-collector": "1",
        })
        collector_url = reverse('admin:admin_views_collector_change', args=(self.collector.pk,))
        response = self.client.post(collector_url, self.post_data)
        # Successful post will redirect
        self.assertEqual(response.status_code, 302)

        # Check that the order values have been applied to the right objects
        self.assertEqual(self.collector.category_set.count(), 4)
        self.assertEqual(Category.objects.get(id=1).order, 14)
        self.assertEqual(Category.objects.get(id=2).order, 13)
        self.assertEqual(Category.objects.get(id=3).order, 1)
        self.assertEqual(Category.objects.get(id=4).order, 0)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class NeverCacheTests(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-colors.xml', 'admin-views-fabrics.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_admin_index(self):
        "Check the never-cache status of the main index"
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(get_max_age(response), 0)

    def test_app_index(self):
        "Check the never-cache status of an application index"
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertEqual(get_max_age(response), 0)

    def test_model_index(self):
        "Check the never-cache status of a model index"
        response = self.client.get(reverse('admin:admin_views_fabric_changelist'))
        self.assertEqual(get_max_age(response), 0)

    def test_model_add(self):
        "Check the never-cache status of a model add page"
        response = self.client.get(reverse('admin:admin_views_fabric_add'))
        self.assertEqual(get_max_age(response), 0)

    def test_model_view(self):
        "Check the never-cache status of a model edit page"
        response = self.client.get(reverse('admin:admin_views_section_change', args=(1,)))
        self.assertEqual(get_max_age(response), 0)

    def test_model_history(self):
        "Check the never-cache status of a model history page"
        response = self.client.get(reverse('admin:admin_views_section_history', args=(1,)))
        self.assertEqual(get_max_age(response), 0)

    def test_model_delete(self):
        "Check the never-cache status of a model delete page"
        response = self.client.get(reverse('admin:admin_views_section_delete', args=(1,)))
        self.assertEqual(get_max_age(response), 0)

    def test_login(self):
        "Check the never-cache status of login views"
        self.client.logout()
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(get_max_age(response), 0)

    def test_logout(self):
        "Check the never-cache status of logout view"
        response = self.client.get(reverse('admin:logout'))
        self.assertEqual(get_max_age(response), 0)

    def test_password_change(self):
        "Check the never-cache status of the password change view"
        self.client.logout()
        response = self.client.get(reverse('admin:password_change'))
        self.assertEqual(get_max_age(response), None)

    def test_password_change_done(self):
        "Check the never-cache status of the password change done view"
        response = self.client.get(reverse('admin:password_change_done'))
        self.assertEqual(get_max_age(response), None)

    def test_JS_i18n(self):
        "Check the never-cache status of the JavaScript i18n view"
        response = self.client.get(reverse('admin:jsi18n'))
        self.assertEqual(get_max_age(response), None)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class PrePopulatedTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_prepopulated_on(self):
        response = self.client.get(reverse('admin:admin_views_prepopulatedpost_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "id: '#id_slug',")
        self.assertContains(response, "field['dependency_ids'].push('#id_title');")
        self.assertContains(response, "id: '#id_prepopulatedsubpost_set-0-subslug',")

    def test_prepopulated_off(self):
        response = self.client.get(reverse('admin:admin_views_prepopulatedpost_change', args=(1,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A Long Title")
        self.assertNotContains(response, "id: '#id_slug'")
        self.assertNotContains(response, "field['dependency_ids'].push('#id_title');")
        self.assertNotContains(response, "id: '#id_prepopulatedsubpost_set-0-subslug',")

    @override_settings(USE_THOUSAND_SEPARATOR=True, USE_L10N=True)
    def test_prepopulated_maxlength_localized(self):
        """
        Regression test for #15938: if USE_THOUSAND_SEPARATOR is set, make sure
        that maxLength (in the JavaScript) is rendered without separators.
        """
        response = self.client.get(reverse('admin:admin_views_prepopulatedpostlargeslug_add'))
        self.assertContains(response, "maxLength: 1000")  # instead of 1,000


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class SeleniumAdminViewsFirefoxTests(AdminSeleniumWebDriverTestCase):

    available_apps = ['admin_views'] + AdminSeleniumWebDriverTestCase.available_apps
    fixtures = ['admin-views-users.xml']
    webdriver_class = 'selenium.webdriver.firefox.webdriver.WebDriver'

    def test_prepopulated_fields(self):
        """
        Ensure that the JavaScript-automated prepopulated fields work with the
        main form and with stacked and tabular inlines.
        Refs #13068, #9264, #9983, #9784.
        """
        self.admin_login(username='super', password='secret', login_url=reverse('admin:index'))
        self.selenium.get('%s%s' % (self.live_server_url,
            reverse('admin:admin_views_mainprepopulated_add')))

        # Main form ----------------------------------------------------------
        self.selenium.find_element_by_css_selector('#id_pubdate').send_keys('2012-02-18')
        self.get_select_option('#id_status', 'option two').click()
        self.selenium.find_element_by_css_selector('#id_name').send_keys(' this is the mAin nÀMë and it\'s awεšome')
        slug1 = self.selenium.find_element_by_css_selector('#id_slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_slug2').get_attribute('value')
        self.assertEqual(slug1, 'main-name-and-its-awesome-2012-02-18')
        self.assertEqual(slug2, 'option-two-main-name-and-its-awesome')

        # Stacked inlines ----------------------------------------------------
        # Initial inline
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-0-pubdate').send_keys('2011-12-17')
        self.get_select_option('#id_relatedprepopulated_set-0-status', 'option one').click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-0-name').send_keys(' here is a sŤāÇkeð   inline !  ')
        slug1 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-0-slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-0-slug2').get_attribute('value')
        self.assertEqual(slug1, 'here-stacked-inline-2011-12-17')
        self.assertEqual(slug2, 'option-one-here-stacked-inline')

        # Add an inline
        self.selenium.find_elements_by_link_text('Add another Related prepopulated')[0].click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-1-pubdate').send_keys('1999-01-25')
        self.get_select_option('#id_relatedprepopulated_set-1-status', 'option two').click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-1-name').send_keys(' now you haVe anöther   sŤāÇkeð  inline with a very ... loooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooog text... ')
        slug1 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-1-slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-1-slug2').get_attribute('value')
        self.assertEqual(slug1, 'now-you-have-another-stacked-inline-very-loooooooo')  # 50 characters maximum for slug1 field
        self.assertEqual(slug2, 'option-two-now-you-have-another-stacked-inline-very-looooooo')  # 60 characters maximum for slug2 field

        # Tabular inlines ----------------------------------------------------
        # Initial inline
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-0-pubdate').send_keys('1234-12-07')
        self.get_select_option('#id_relatedprepopulated_set-2-0-status', 'option two').click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-0-name').send_keys('And now, with a tÃbűlaŘ inline !!!')
        slug1 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-0-slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-0-slug2').get_attribute('value')
        self.assertEqual(slug1, 'and-now-tabular-inline-1234-12-07')
        self.assertEqual(slug2, 'option-two-and-now-tabular-inline')

        # Add an inline
        self.selenium.find_elements_by_link_text('Add another Related prepopulated')[1].click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-1-pubdate').send_keys('1981-08-22')
        self.get_select_option('#id_relatedprepopulated_set-2-1-status', 'option one').click()
        self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-1-name').send_keys('a tÃbűlaŘ inline with ignored ;"&*^\%$#@-/`~ characters')
        slug1 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-1-slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_relatedprepopulated_set-2-1-slug2').get_attribute('value')
        self.assertEqual(slug1, 'tabular-inline-ignored-characters-1981-08-22')
        self.assertEqual(slug2, 'option-one-tabular-inline-ignored-characters')

        # Save and check that everything is properly stored in the database
        self.selenium.find_element_by_xpath('//input[@value="Save"]').click()
        self.wait_page_loaded()
        self.assertEqual(MainPrepopulated.objects.all().count(), 1)
        MainPrepopulated.objects.get(
            name=' this is the mAin nÀMë and it\'s awεšome',
            pubdate='2012-02-18',
            status='option two',
            slug1='main-name-and-its-awesome-2012-02-18',
            slug2='option-two-main-name-and-its-awesome',
        )
        self.assertEqual(RelatedPrepopulated.objects.all().count(), 4)
        RelatedPrepopulated.objects.get(
            name=' here is a sŤāÇkeð   inline !  ',
            pubdate='2011-12-17',
            status='option one',
            slug1='here-stacked-inline-2011-12-17',
            slug2='option-one-here-stacked-inline',
        )
        RelatedPrepopulated.objects.get(
            name=' now you haVe anöther   sŤāÇkeð  inline with a very ... loooooooooooooooooo',  # 75 characters in name field
            pubdate='1999-01-25',
            status='option two',
            slug1='now-you-have-another-stacked-inline-very-loooooooo',
            slug2='option-two-now-you-have-another-stacked-inline-very-looooooo',
        )
        RelatedPrepopulated.objects.get(
            name='And now, with a tÃbűlaŘ inline !!!',
            pubdate='1234-12-07',
            status='option two',
            slug1='and-now-tabular-inline-1234-12-07',
            slug2='option-two-and-now-tabular-inline',
        )
        RelatedPrepopulated.objects.get(
            name='a tÃbűlaŘ inline with ignored ;"&*^\%$#@-/`~ characters',
            pubdate='1981-08-22',
            status='option one',
            slug1='tabular-inline-ignored-characters-1981-08-22',
            slug2='option-one-tabular-inline-ignored-characters',
        )

    def test_populate_existing_object(self):
        """
        Ensure that the prepopulation works for existing objects too, as long
        as the original field is empty.
        Refs #19082.
        """
        # Slugs are empty to start with.
        item = MainPrepopulated.objects.create(
            name=' this is the mAin nÀMë',
            pubdate='2012-02-18',
            status='option two',
            slug1='',
            slug2='',
        )
        self.admin_login(username='super',
                         password='secret',
                         login_url=reverse('admin:index'))

        object_url = '%s%s' % (
            self.live_server_url,
            reverse('admin:admin_views_mainprepopulated_change', args=(item.id,)))

        self.selenium.get(object_url)
        self.selenium.find_element_by_css_selector('#id_name').send_keys(' the best')

        # The slugs got prepopulated since they were originally empty
        slug1 = self.selenium.find_element_by_css_selector('#id_slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_slug2').get_attribute('value')
        self.assertEqual(slug1, 'main-name-best-2012-02-18')
        self.assertEqual(slug2, 'option-two-main-name-best')

        # Save the object
        self.selenium.find_element_by_xpath('//input[@value="Save"]').click()
        self.wait_page_loaded()

        self.selenium.get(object_url)
        self.selenium.find_element_by_css_selector('#id_name').send_keys(' hello')

        # The slugs got prepopulated didn't change since they were originally not empty
        slug1 = self.selenium.find_element_by_css_selector('#id_slug1').get_attribute('value')
        slug2 = self.selenium.find_element_by_css_selector('#id_slug2').get_attribute('value')
        self.assertEqual(slug1, 'main-name-best-2012-02-18')
        self.assertEqual(slug2, 'option-two-main-name-best')

    def test_collapsible_fieldset(self):
        """
        Test that the 'collapse' class in fieldsets definition allows to
        show/hide the appropriate field section.
        """
        self.admin_login(username='super', password='secret', login_url=reverse('admin:index'))
        self.selenium.get('%s%s' % (self.live_server_url,
            reverse('admin:admin_views_article_add')))
        self.assertFalse(self.selenium.find_element_by_id('id_title').is_displayed())
        self.selenium.find_elements_by_link_text('Show')[0].click()
        self.assertTrue(self.selenium.find_element_by_id('id_title').is_displayed())
        self.assertEqual(
            self.selenium.find_element_by_id('fieldsetcollapser0').text,
            "Hide"
        )

    def test_first_field_focus(self):
        """JavaScript-assisted auto-focus on first usable form field."""
        # First form field has a single widget
        self.admin_login(username='super', password='secret', login_url=reverse('admin:index'))
        self.selenium.get('%s%s' % (self.live_server_url,
            reverse('admin:admin_views_picture_add')))
        self.assertEqual(
            self.selenium.switch_to.active_element,
            self.selenium.find_element_by_id('id_name')
        )

        # First form field has a MultiWidget
        self.selenium.get('%s%s' % (self.live_server_url,
            reverse('admin:admin_views_reservation_add')))
        self.assertEqual(
            self.selenium.switch_to.active_element,
            self.selenium.find_element_by_id('id_start_date_0')
        )

    def test_cancel_delete_confirmation(self):
        "Cancelling the deletion of an object takes the user back one page."
        pizza = Pizza.objects.create(name="Double Cheese")
        url = reverse('admin:admin_views_pizza_change', args=(pizza.id,))
        full_url = '%s%s' % (self.live_server_url, url)
        self.admin_login(username='super', password='secret', login_url=reverse('admin:index'))
        self.selenium.get(full_url)
        self.selenium.find_element_by_class_name('deletelink').click()
        self.selenium.find_element_by_class_name('cancel-link').click()
        self.wait_page_loaded()
        self.assertEqual(self.selenium.current_url, full_url)
        self.assertEqual(Pizza.objects.count(), 1)

    def test_cancel_delete_related_confirmation(self):
        """
        Cancelling the deletion of an object with relations takes the user back
        one page.
        """
        pizza = Pizza.objects.create(name="Double Cheese")
        topping1 = Topping.objects.create(name="Cheddar")
        topping2 = Topping.objects.create(name="Mozzarella")
        pizza.toppings.add(topping1, topping2)
        url = reverse('admin:admin_views_pizza_change', args=(pizza.id,))
        full_url = '%s%s' % (self.live_server_url, url)
        self.admin_login(username='super', password='secret', login_url=reverse('admin:index'))
        self.selenium.get(full_url)
        self.selenium.find_element_by_class_name('deletelink').click()
        self.selenium.find_element_by_class_name('cancel-link').click()
        self.wait_page_loaded()
        self.assertEqual(self.selenium.current_url, full_url)
        self.assertEqual(Pizza.objects.count(), 1)
        self.assertEqual(Topping.objects.count(), 2)


class SeleniumAdminViewsChromeTests(SeleniumAdminViewsFirefoxTests):
    webdriver_class = 'selenium.webdriver.chrome.webdriver.WebDriver'


class SeleniumAdminViewsIETests(SeleniumAdminViewsFirefoxTests):
    webdriver_class = 'selenium.webdriver.ie.webdriver.WebDriver'


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class ReadonlyTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_readonly_get(self):
        response = self.client.get(reverse('admin:admin_views_post_add'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="posted"')
        # 3 fields + 2 submit buttons + 5 inline management form fields, + 2
        # hidden fields for inlines + 1 field for the inline + 2 empty form
        self.assertContains(response, "<input", count=15)
        self.assertContains(response, formats.localize(datetime.date.today()))
        self.assertContains(response,
            "<label>Awesomeness level:</label>")
        self.assertContains(response, "Very awesome.")
        self.assertContains(response, "Unknown coolness.")
        self.assertContains(response, "foo")

        # Checks that multiline text in a readonly field gets <br /> tags
        self.assertContains(response, "Multiline<br />test<br />string")
        self.assertContains(response, "<p>Multiline<br />html<br />content</p>", html=True)
        self.assertContains(response, "InlineMultiline<br />test<br />string")

        self.assertContains(response,
            formats.localize(datetime.date.today() - datetime.timedelta(days=7)))

        self.assertContains(response, '<div class="form-row field-coolness">')
        self.assertContains(response, '<div class="form-row field-awesomeness_level">')
        self.assertContains(response, '<div class="form-row field-posted">')
        self.assertContains(response, '<div class="form-row field-value">')
        self.assertContains(response, '<div class="form-row">')
        self.assertContains(response, '<p class="help">', 3)
        self.assertContains(response, '<p class="help">Some help text for the title (with unicode ŠĐĆŽćžšđ)</p>', html=True)
        self.assertContains(response, '<p class="help">Some help text for the content (with unicode ŠĐĆŽćžšđ)</p>', html=True)
        self.assertContains(response, '<p class="help">Some help text for the date (with unicode ŠĐĆŽćžšđ)</p>', html=True)

        p = Post.objects.create(title="I worked on readonly_fields", content="Its good stuff")
        response = self.client.get(reverse('admin:admin_views_post_change', args=(p.pk,)))
        self.assertContains(response, "%d amount of cool" % p.pk)

    def test_readonly_post(self):
        data = {
            "title": "Django Got Readonly Fields",
            "content": "This is an incredible development.",
            "link_set-TOTAL_FORMS": "1",
            "link_set-INITIAL_FORMS": "0",
            "link_set-MAX_NUM_FORMS": "0",
        }
        response = self.client.post(reverse('admin:admin_views_post_add'), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 1)
        p = Post.objects.get()
        self.assertEqual(p.posted, datetime.date.today())

        data["posted"] = "10-8-1990"  # some date that's not today
        response = self.client.post(reverse('admin:admin_views_post_add'), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 2)
        p = Post.objects.order_by('-id')[0]
        self.assertEqual(p.posted, datetime.date.today())

    def test_readonly_manytomany(self):
        "Regression test for #13004"
        response = self.client.get(reverse('admin:admin_views_pizza_add'))
        self.assertEqual(response.status_code, 200)

    def test_user_password_change_limited_queryset(self):
        su = User.objects.filter(is_superuser=True)[0]
        response = self.client.get(reverse('admin2:auth_user_password_change', args=(su.pk,)))
        self.assertEqual(response.status_code, 404)

    def test_change_form_renders_correct_null_choice_value(self):
        """
        Regression test for #17911.
        """
        choice = Choice.objects.create(choice=None)
        response = self.client.get(reverse('admin:admin_views_choice_change', args=(choice.pk,)))
        self.assertContains(response, '<p>No opinion</p>', html=True)
        self.assertNotContains(response, '<p>(None)</p>')

    def test_readonly_backwards_ref(self):
        """
        Regression test for #16433 - backwards references for related objects
        broke if the related field is read-only due to the help_text attribute
        """
        topping = Topping.objects.create(name='Salami')
        pizza = Pizza.objects.create(name='Americano')
        pizza.toppings.add(topping)
        response = self.client.get(reverse('admin:admin_views_topping_add'))
        self.assertEqual(response.status_code, 200)

    def test_readonly_field_overrides(self):
        """
        Regression test for #22087 - ModelForm Meta overrides are ignored by
        AdminReadonlyField
        """
        p = FieldOverridePost.objects.create(title="Test Post", content="Test Content")
        response = self.client.get(reverse('admin:admin_views_fieldoverridepost_change', args=(p.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<p class="help">Overridden help text for the date</p>')
        self.assertContains(response, '<label for="id_public">Overridden public label:</label>', html=True)
        self.assertNotContains(response, "Some help text for the date (with unicode ŠĐĆŽćžšđ)")

    def test_correct_autoescaping(self):
        """
        Make sure that non-field readonly elements are properly autoescaped (#24461)
        """
        section = Section.objects.create(name='<a>evil</a>')
        response = self.client.get(reverse('admin:admin_views_section_change', args=(section.pk,)))
        self.assertNotContains(response, "<a>evil</a>", status_code=200)
        self.assertContains(response, "&lt;a&gt;evil&lt;/a&gt;", status_code=200)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class LimitChoicesToInAdminTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_limit_choices_to_as_callable(self):
        """Test for ticket 2445 changes to admin."""
        threepwood = Character.objects.create(
            username='threepwood',
            last_action=datetime.datetime.today() + datetime.timedelta(days=1),
        )
        marley = Character.objects.create(
            username='marley',
            last_action=datetime.datetime.today() - datetime.timedelta(days=1),
        )
        response = self.client.get(reverse('admin:admin_views_stumpjoke_add'))
        # The allowed option should appear twice; the limited option should not appear.
        self.assertContains(response, threepwood.username, count=2)
        self.assertNotContains(response, marley.username)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class RawIdFieldsTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_limit_choices_to(self):
        """Regression test for 14880"""
        actor = Actor.objects.create(name="Palin", age=27)
        Inquisition.objects.create(expected=True,
                                   leader=actor,
                                   country="England")
        Inquisition.objects.create(expected=False,
                                   leader=actor,
                                   country="Spain")
        response = self.client.get(reverse('admin:admin_views_sketch_add'))
        # Find the link
        m = re.search(br'<a href="([^"]*)"[^>]* id="lookup_id_inquisition"', response.content)
        self.assertTrue(m)  # Got a match
        popup_url = m.groups()[0].decode().replace("&amp;", "&")

        # Handle relative links
        popup_url = urljoin(response.request['PATH_INFO'], popup_url)
        # Get the popup and verify the correct objects show up in the resulting
        # page. This step also tests integers, strings and booleans in the
        # lookup query string; in model we define inquisition field to have a
        # limit_choices_to option that includes a filter on a string field
        # (inquisition__actor__name), a filter on an integer field
        # (inquisition__actor__age), and a filter on a boolean field
        # (inquisition__expected).
        response2 = self.client.get(popup_url)
        self.assertContains(response2, "Spain")
        self.assertNotContains(response2, "England")

    def test_limit_choices_to_isnull_false(self):
        """Regression test for 20182"""
        Actor.objects.create(name="Palin", age=27)
        Actor.objects.create(name="Kilbraken", age=50, title="Judge")
        response = self.client.get(reverse('admin:admin_views_sketch_add'))
        # Find the link
        m = re.search(br'<a href="([^"]*)"[^>]* id="lookup_id_defendant0"', response.content)
        self.assertTrue(m)  # Got a match
        popup_url = m.groups()[0].decode().replace("&amp;", "&")

        # Handle relative links
        popup_url = urljoin(response.request['PATH_INFO'], popup_url)
        # Get the popup and verify the correct objects show up in the resulting
        # page. This step tests field__isnull=0 gets parsed correctly from the
        # lookup query string; in model we define defendant0 field to have a
        # limit_choices_to option that includes "actor__title__isnull=False".
        response2 = self.client.get(popup_url)
        self.assertContains(response2, "Kilbraken")
        self.assertNotContains(response2, "Palin")

    def test_limit_choices_to_isnull_true(self):
        """Regression test for 20182"""
        Actor.objects.create(name="Palin", age=27)
        Actor.objects.create(name="Kilbraken", age=50, title="Judge")
        response = self.client.get(reverse('admin:admin_views_sketch_add'))
        # Find the link
        m = re.search(br'<a href="([^"]*)"[^>]* id="lookup_id_defendant1"', response.content)
        self.assertTrue(m)  # Got a match
        popup_url = m.groups()[0].decode().replace("&amp;", "&")

        # Handle relative links
        popup_url = urljoin(response.request['PATH_INFO'], popup_url)
        # Get the popup and verify the correct objects show up in the resulting
        # page. This step tests field__isnull=1 gets parsed correctly from the
        # lookup query string; in model we define defendant1 field to have a
        # limit_choices_to option that includes "actor__title__isnull=True".
        response2 = self.client.get(popup_url)
        self.assertNotContains(response2, "Kilbraken")
        self.assertContains(response2, "Palin")


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class UserAdminTest(TestCase):
    """
    Tests user CRUD functionality.
    """
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_save_button(self):
        user_count = User.objects.count()
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'newpassword',
        })
        new_user = User.objects.order_by('-id')[0]
        self.assertRedirects(response, reverse('admin:auth_user_change', args=(new_user.pk,)))
        self.assertEqual(User.objects.count(), user_count + 1)
        self.assertTrue(new_user.has_usable_password())

    def test_save_continue_editing_button(self):
        user_count = User.objects.count()
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'newpassword',
            '_continue': '1',
        })
        new_user = User.objects.order_by('-id')[0]
        self.assertRedirects(response, reverse('admin:auth_user_change', args=(new_user.pk,)))
        self.assertEqual(User.objects.count(), user_count + 1)
        self.assertTrue(new_user.has_usable_password())

    def test_password_mismatch(self):
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'mismatch',
        })
        self.assertEqual(response.status_code, 200)
        adminform = response.context['adminform']
        self.assertNotIn('password', adminform.form.errors)
        self.assertEqual(adminform.form.errors['password2'],
            ["The two password fields didn't match."])

    def test_user_fk_add_popup(self):
        """User addition through a FK popup should return the appropriate JavaScript response."""
        response = self.client.get(reverse('admin:admin_views_album_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:auth_user_add'))
        self.assertContains(response, 'class="related-widget-wrapper-link add-related" id="add_id_owner"')
        response = self.client.get(reverse('admin:auth_user_add') + '?_popup=1')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_continue"')
        self.assertNotContains(response, 'name="_addanother"')
        data = {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'newpassword',
            '_popup': '1',
            '_save': '1',
        }
        response = self.client.post(reverse('admin:auth_user_add') + '?_popup=1', data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dismissAddRelatedObjectPopup')

    def test_user_fk_change_popup(self):
        """User change through a FK popup should return the appropriate JavaScript response."""
        response = self.client.get(reverse('admin:admin_views_album_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:auth_user_change', args=('__fk__',)))
        self.assertContains(response, 'class="related-widget-wrapper-link change-related" id="change_id_owner"')
        user = User.objects.get(username='changeuser')
        url = reverse('admin:auth_user_change', args=(user.pk,)) + '?_popup=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_continue"')
        self.assertNotContains(response, 'name="_addanother"')
        data = {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'newpassword',
            'last_login_0': '2007-05-30',
            'last_login_1': '13:20:10',
            'date_joined_0': '2007-05-30',
            'date_joined_1': '13:20:10',
            '_popup': '1',
            '_save': '1',
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dismissChangeRelatedObjectPopup')

    def test_user_fk_delete_popup(self):
        """User deletion through a FK popup should return the appropriate JavaScript response."""
        response = self.client.get(reverse('admin:admin_views_album_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:auth_user_delete', args=('__fk__',)))
        self.assertContains(response, 'class="related-widget-wrapper-link change-related" id="change_id_owner"')
        user = User.objects.get(username='changeuser')
        url = reverse('admin:auth_user_delete', args=(user.pk,)) + '?_popup=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = {
            'post': 'yes',
            '_popup': '1',
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dismissDeleteRelatedObjectPopup')

    def test_save_add_another_button(self):
        user_count = User.objects.count()
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'newuser',
            'password1': 'newpassword',
            'password2': 'newpassword',
            '_addanother': '1',
        })
        new_user = User.objects.order_by('-id')[0]
        self.assertRedirects(response, reverse('admin:auth_user_add'))
        self.assertEqual(User.objects.count(), user_count + 1)
        self.assertTrue(new_user.has_usable_password())

    def test_user_permission_performance(self):
        u = User.objects.all()[0]

        # Don't depend on a warm cache, see #17377.
        ContentType.objects.clear_cache()

        with self.assertNumQueries(10):
            response = self.client.get(reverse('admin:auth_user_change', args=(u.pk,)))
            self.assertEqual(response.status_code, 200)

    def test_form_url_present_in_context(self):
        u = User.objects.all()[0]
        response = self.client.get(reverse('admin3:auth_user_password_change', args=(u.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form_url'], 'pony')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class GroupAdminTest(TestCase):
    """
    Tests group CRUD functionality.
    """
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_save_button(self):
        group_count = Group.objects.count()
        response = self.client.post(reverse('admin:auth_group_add'), {
            'name': 'newgroup',
        })

        Group.objects.order_by('-id')[0]
        self.assertRedirects(response, reverse('admin:auth_group_changelist'))
        self.assertEqual(Group.objects.count(), group_count + 1)

    def test_group_permission_performance(self):
        g = Group.objects.create(name="test_group")

        # Ensure no queries are skipped due to cached content type for Group.
        ContentType.objects.clear_cache()

        with self.assertNumQueries(8):
            response = self.client.get(reverse('admin:auth_group_change', args=(g.pk,)))
            self.assertEqual(response.status_code, 200)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class CSSTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_field_prefix_css_classes(self):
        """
        Ensure that fields have a CSS class name with a 'field-' prefix.
        Refs #16371.
        """
        response = self.client.get(reverse('admin:admin_views_post_add'))

        # The main form
        self.assertContains(response, 'class="form-row field-title"')
        self.assertContains(response, 'class="form-row field-content"')
        self.assertContains(response, 'class="form-row field-public"')
        self.assertContains(response, 'class="form-row field-awesomeness_level"')
        self.assertContains(response, 'class="form-row field-coolness"')
        self.assertContains(response, 'class="form-row field-value"')
        self.assertContains(response, 'class="form-row"')  # The lambda function

        # The tabular inline
        self.assertContains(response, '<td class="field-url">')
        self.assertContains(response, '<td class="field-posted">')

    def test_index_css_classes(self):
        """
        Ensure that CSS class names are used for each app and model on the
        admin index pages.
        Refs #17050.
        """
        # General index page
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, '<div class="app-admin_views module">')
        self.assertContains(response, '<tr class="model-actor">')
        self.assertContains(response, '<tr class="model-album">')

        # App index page
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertContains(response, '<div class="app-admin_views module">')
        self.assertContains(response, '<tr class="model-actor">')
        self.assertContains(response, '<tr class="model-album">')

    def test_app_model_in_form_body_class(self):
        """
        Ensure app and model tag are correctly read by change_form template
        """
        response = self.client.get(reverse('admin:admin_views_section_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,
            '<body class=" app-admin_views model-section ')

    def test_app_model_in_list_body_class(self):
        """
        Ensure app and model tag are correctly read by change_list template
        """
        response = self.client.get(reverse('admin:admin_views_section_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,
            '<body class=" app-admin_views model-section ')

    def test_app_model_in_delete_confirmation_body_class(self):
        """
        Ensure app and model tag are correctly read by delete_confirmation
        template
        """
        response = self.client.get(
            reverse('admin:admin_views_section_delete', args=(1,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,
            '<body class=" app-admin_views model-section ')

    def test_app_model_in_app_index_body_class(self):
        """
        Ensure app and model tag are correctly read by app_index template
        """
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<body class=" dashboard app-admin_views')

    def test_app_model_in_delete_selected_confirmation_body_class(self):
        """
        Ensure app and model tag are correctly read by
        delete_selected_confirmation template
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'delete_selected',
            'index': 0,
        }
        response = self.client.post(reverse('admin:admin_views_section_changelist'),
            action_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response,
            '<body class=" app-admin_views model-section ')

    def test_changelist_field_classes(self):
        """
        Cells of the change list table should contain the field name in their class attribute
        Refs #11195.
        """
        Podcast.objects.create(name="Django Dose",
            release_date=datetime.date.today())
        response = self.client.get(reverse('admin:admin_views_podcast_changelist'))
        self.assertContains(
            response, '<th class="field-name">')
        self.assertContains(
            response, '<td class="field-release_date nowrap">')
        self.assertContains(
            response, '<td class="action-checkbox">')


try:
    import docutils
except ImportError:
    docutils = None


@unittest.skipUnless(docutils, "no docutils installed.")
@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
@modify_settings(INSTALLED_APPS={'append': ['django.contrib.admindocs', 'django.contrib.flatpages']})
class AdminDocsTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_tags(self):
        response = self.client.get(reverse('django-admindocs-tags'))

        # The builtin tag group exists
        self.assertContains(response, "<h2>Built-in tags</h2>", count=2, html=True)

        # A builtin tag exists in both the index and detail
        self.assertContains(response, '<h3 id="built_in-autoescape">autoescape</h3>', html=True)
        self.assertContains(response, '<li><a href="#built_in-autoescape">autoescape</a></li>', html=True)

        # An app tag exists in both the index and detail
        self.assertContains(response, '<h3 id="flatpages-get_flatpages">get_flatpages</h3>', html=True)
        self.assertContains(response, '<li><a href="#flatpages-get_flatpages">get_flatpages</a></li>', html=True)

        # The admin list tag group exists
        self.assertContains(response, "<h2>admin_list</h2>", count=2, html=True)

        # An admin list tag exists in both the index and detail
        self.assertContains(response, '<h3 id="admin_list-admin_actions">admin_actions</h3>', html=True)
        self.assertContains(response, '<li><a href="#admin_list-admin_actions">admin_actions</a></li>', html=True)

    def test_filters(self):
        response = self.client.get(reverse('django-admindocs-filters'))

        # The builtin filter group exists
        self.assertContains(response, "<h2>Built-in filters</h2>", count=2, html=True)

        # A builtin filter exists in both the index and detail
        self.assertContains(response, '<h3 id="built_in-add">add</h3>', html=True)
        self.assertContains(response, '<li><a href="#built_in-add">add</a></li>', html=True)


@override_settings(
    PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls",
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    }],
    USE_I18N=False,
)
class ValidXHTMLTests(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_lang_name_present(self):
        response = self.client.get(reverse('admin:app_list', args=('admin_views',)))
        self.assertNotContains(response, ' lang=""')
        self.assertNotContains(response, ' xml:lang=""')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
                   ROOT_URLCONF="admin_views.urls",
                   USE_THOUSAND_SEPARATOR=True, USE_L10N=True)
class DateHierarchyTests(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def tearDown(self):
        formats.reset_format_cache()

    def assert_non_localized_year(self, response, year):
        """Ensure that the year is not localized with
        USE_THOUSAND_SEPARATOR. Refs #15234.
        """
        self.assertNotContains(response, formats.number_format(year))

    def assert_contains_year_link(self, response, date):
        self.assertContains(response, '?release_date__year=%d"' % (date.year,))

    def assert_contains_month_link(self, response, date):
        self.assertContains(
            response, '?release_date__month=%d&amp;release_date__year=%d"' % (
                date.month, date.year))

    def assert_contains_day_link(self, response, date):
        self.assertContains(
            response, '?release_date__day=%d&amp;'
            'release_date__month=%d&amp;release_date__year=%d"' % (
                date.day, date.month, date.year))

    def test_empty(self):
        """
        Ensure that no date hierarchy links display with empty changelist.
        """
        response = self.client.get(
            reverse('admin:admin_views_podcast_changelist'))
        self.assertNotContains(response, 'release_date__year=')
        self.assertNotContains(response, 'release_date__month=')
        self.assertNotContains(response, 'release_date__day=')

    def test_single(self):
        """
        Ensure that single day-level date hierarchy appears for single object.
        """
        DATE = datetime.date(2000, 6, 30)
        Podcast.objects.create(release_date=DATE)
        url = reverse('admin:admin_views_podcast_changelist')
        response = self.client.get(url)
        self.assert_contains_day_link(response, DATE)
        self.assert_non_localized_year(response, 2000)

    def test_within_month(self):
        """
        Ensure that day-level links appear for changelist within single month.
        """
        DATES = (datetime.date(2000, 6, 30),
                 datetime.date(2000, 6, 15),
                 datetime.date(2000, 6, 3))
        for date in DATES:
            Podcast.objects.create(release_date=date)
        url = reverse('admin:admin_views_podcast_changelist')
        response = self.client.get(url)
        for date in DATES:
            self.assert_contains_day_link(response, date)
        self.assert_non_localized_year(response, 2000)

    def test_within_year(self):
        """
        Ensure that month-level links appear for changelist within single year.
        """
        DATES = (datetime.date(2000, 1, 30),
                 datetime.date(2000, 3, 15),
                 datetime.date(2000, 5, 3))
        for date in DATES:
            Podcast.objects.create(release_date=date)
        url = reverse('admin:admin_views_podcast_changelist')
        response = self.client.get(url)
        # no day-level links
        self.assertNotContains(response, 'release_date__day=')
        for date in DATES:
            self.assert_contains_month_link(response, date)
        self.assert_non_localized_year(response, 2000)

    def test_multiple_years(self):
        """
        Ensure that year-level links appear for year-spanning changelist.
        """
        DATES = (datetime.date(2001, 1, 30),
                 datetime.date(2003, 3, 15),
                 datetime.date(2005, 5, 3))
        for date in DATES:
            Podcast.objects.create(release_date=date)
        response = self.client.get(
            reverse('admin:admin_views_podcast_changelist'))
        # no day/month-level links
        self.assertNotContains(response, 'release_date__day=')
        self.assertNotContains(response, 'release_date__month=')
        for date in DATES:
            self.assert_contains_year_link(response, date)

        # and make sure GET parameters still behave correctly
        for date in DATES:
            url = '%s?release_date__year=%d' % (
                  reverse('admin:admin_views_podcast_changelist'),
                  date.year)
            response = self.client.get(url)
            self.assert_contains_month_link(response, date)
            self.assert_non_localized_year(response, 2000)
            self.assert_non_localized_year(response, 2003)
            self.assert_non_localized_year(response, 2005)

            url = '%s?release_date__year=%d&release_date__month=%d' % (
                  reverse('admin:admin_views_podcast_changelist'),
                  date.year, date.month)
            response = self.client.get(url)
            self.assert_contains_day_link(response, date)
            self.assert_non_localized_year(response, 2000)
            self.assert_non_localized_year(response, 2003)
            self.assert_non_localized_year(response, 2005)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminCustomSaveRelatedTests(TestCase):
    """
    Ensure that one can easily customize the way related objects are saved.
    Refs #16115.
    """
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_should_be_able_to_edit_related_objects_on_add_view(self):
        post = {
            'child_set-TOTAL_FORMS': '3',
            'child_set-INITIAL_FORMS': '0',
            'name': 'Josh Stone',
            'child_set-0-name': 'Paul',
            'child_set-1-name': 'Catherine',
        }
        self.client.post(reverse('admin:admin_views_parent_add'), post)
        self.assertEqual(1, Parent.objects.count())
        self.assertEqual(2, Child.objects.count())

        children_names = list(Child.objects.order_by('name').values_list('name', flat=True))

        self.assertEqual('Josh Stone', Parent.objects.latest('id').name)
        self.assertEqual(['Catherine Stone', 'Paul Stone'], children_names)

    def test_should_be_able_to_edit_related_objects_on_change_view(self):
        parent = Parent.objects.create(name='Josh Stone')
        paul = Child.objects.create(parent=parent, name='Paul')
        catherine = Child.objects.create(parent=parent, name='Catherine')
        post = {
            'child_set-TOTAL_FORMS': '5',
            'child_set-INITIAL_FORMS': '2',
            'name': 'Josh Stone',
            'child_set-0-name': 'Paul',
            'child_set-0-id': paul.id,
            'child_set-1-name': 'Catherine',
            'child_set-1-id': catherine.id,
        }
        self.client.post(reverse('admin:admin_views_parent_change', args=(parent.id,)), post)

        children_names = list(Child.objects.order_by('name').values_list('name', flat=True))

        self.assertEqual('Josh Stone', Parent.objects.latest('id').name)
        self.assertEqual(['Catherine Stone', 'Paul Stone'], children_names)

    def test_should_be_able_to_edit_related_objects_on_changelist_view(self):
        parent = Parent.objects.create(name='Josh Rock')
        Child.objects.create(parent=parent, name='Paul')
        Child.objects.create(parent=parent, name='Catherine')
        post = {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
            'form-MAX_NUM_FORMS': '0',
            'form-0-id': parent.id,
            'form-0-name': 'Josh Stone',
            '_save': 'Save'
        }

        self.client.post(reverse('admin:admin_views_parent_changelist'), post)
        children_names = list(Child.objects.order_by('name').values_list('name', flat=True))

        self.assertEqual('Josh Stone', Parent.objects.latest('id').name)
        self.assertEqual(['Catherine Stone', 'Paul Stone'], children_names)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewLogoutTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_client_logout_url_can_be_used_to_login(self):
        response = self.client.get(reverse('admin:logout'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/logged_out.html')
        self.assertEqual(response.request['PATH_INFO'], reverse('admin:logout'))

        # we are now logged out
        response = self.client.get(reverse('admin:logout'))
        self.assertEqual(response.status_code, 302)  # we should be redirected to the login page.

        # follow the redirect and test results.
        response = self.client.get(reverse('admin:logout'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin/login.html')
        self.assertEqual(response.request['PATH_INFO'], reverse('admin:login'))
        self.assertContains(response, '<input type="hidden" name="next" value="%s" />' % reverse('admin:index'))


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminUserMessageTest(TestCase):
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def send_message(self, level):
        """
        Helper that sends a post to the dummy test methods and asserts that a
        message with the level has appeared in the response.
        """
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'message_%s' % level,
            'index': 0,
        }

        response = self.client.post(reverse('admin:admin_views_usermessenger_changelist'),
                                    action_data, follow=True)
        self.assertContains(response,
                            '<li class="%s">Test %s</li>' % (level, level),
                            html=True)

    @override_settings(MESSAGE_LEVEL=10)  # Set to DEBUG for this request
    def test_message_debug(self):
        self.send_message('debug')

    def test_message_info(self):
        self.send_message('info')

    def test_message_success(self):
        self.send_message('success')

    def test_message_warning(self):
        self.send_message('warning')

    def test_message_error(self):
        self.send_message('error')

    def test_message_extra_tags(self):
        action_data = {
            ACTION_CHECKBOX_NAME: [1],
            'action': 'message_extra_tags',
            'index': 0,
        }

        response = self.client.post(reverse('admin:admin_views_usermessenger_changelist'),
                                    action_data, follow=True)
        self.assertContains(response,
                            '<li class="extra_tag info">Test tags</li>',
                            html=True)


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminKeepChangeListFiltersTests(TestCase):
    fixtures = ['admin-views-users.xml']
    admin_site = site

    def setUp(self):
        self.client.login(username='super', password='secret')

    def assertURLEqual(self, url1, url2):
        """
        Assert that two URLs are equal despite the ordering
        of their querystring. Refs #22360.
        """
        parsed_url1 = urlparse(url1)
        path1 = parsed_url1.path
        parsed_qs1 = dict(parse_qsl(parsed_url1.query))

        parsed_url2 = urlparse(url2)
        path2 = parsed_url2.path
        parsed_qs2 = dict(parse_qsl(parsed_url2.query))

        for parsed_qs in [parsed_qs1, parsed_qs2]:
            if '_changelist_filters' in parsed_qs:
                changelist_filters = parsed_qs['_changelist_filters']
                parsed_filters = dict(parse_qsl(changelist_filters))
                parsed_qs['_changelist_filters'] = parsed_filters

        self.assertEqual(path1, path2)
        self.assertEqual(parsed_qs1, parsed_qs2)

    def test_assert_url_equal(self):
        # Test equality.
        change_user_url = reverse('admin:auth_user_change', args=(105,))
        self.assertURLEqual(
            'http://testserver{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url),
            'http://testserver{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url)
        )

        # Test inequality.
        with self.assertRaises(AssertionError):
            self.assertURLEqual(
                'http://testserver{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url),
                'http://testserver{}?_changelist_filters=is_staff__exact%3D1%26is_superuser__exact%3D1'.format(change_user_url)
            )

        # Ignore scheme and host.
        self.assertURLEqual(
            'http://testserver{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url),
            '{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url)
        )

        # Ignore ordering of querystring.
        self.assertURLEqual(
            '{}?is_staff__exact=0&is_superuser__exact=0'.format(reverse('admin:auth_user_changelist')),
            '{}?is_superuser__exact=0&is_staff__exact=0'.format(reverse('admin:auth_user_changelist'))
        )

        # Ignore ordering of _changelist_filters.
        self.assertURLEqual(
            '{}?_changelist_filters=is_staff__exact%3D0%26is_superuser__exact%3D0'.format(change_user_url),
            '{}?_changelist_filters=is_superuser__exact%3D0%26is_staff__exact%3D0'.format(change_user_url)
        )

    def get_changelist_filters(self):
        return {
            'is_superuser__exact': 0,
            'is_staff__exact': 0,
        }

    def get_changelist_filters_querystring(self):
        return urlencode(self.get_changelist_filters())

    def get_preserved_filters_querystring(self):
        return urlencode({
            '_changelist_filters': self.get_changelist_filters_querystring()
        })

    def get_sample_user_id(self):
        return 104

    def get_changelist_url(self):
        return '%s?%s' % (
            reverse('admin:auth_user_changelist',
                    current_app=self.admin_site.name),
            self.get_changelist_filters_querystring(),
        )

    def get_add_url(self):
        return '%s?%s' % (
            reverse('admin:auth_user_add',
                    current_app=self.admin_site.name),
            self.get_preserved_filters_querystring(),
        )

    def get_change_url(self, user_id=None):
        if user_id is None:
            user_id = self.get_sample_user_id()
        return "%s?%s" % (
            reverse('admin:auth_user_change', args=(user_id,),
                    current_app=self.admin_site.name),
            self.get_preserved_filters_querystring(),
        )

    def get_history_url(self, user_id=None):
        if user_id is None:
            user_id = self.get_sample_user_id()
        return "%s?%s" % (
            reverse('admin:auth_user_history', args=(user_id,),
                    current_app=self.admin_site.name),
            self.get_preserved_filters_querystring(),
        )

    def get_delete_url(self, user_id=None):
        if user_id is None:
            user_id = self.get_sample_user_id()
        return "%s?%s" % (
            reverse('admin:auth_user_delete', args=(user_id,),
                    current_app=self.admin_site.name),
            self.get_preserved_filters_querystring(),
        )

    def test_changelist_view(self):
        response = self.client.get(self.get_changelist_url())
        self.assertEqual(response.status_code, 200)

        # Check the `change_view` link has the correct querystring.
        detail_link = re.search(
            '<a href="(.*?)">joepublic</a>',
            force_text(response.content)
        )
        self.assertURLEqual(detail_link.group(1), self.get_change_url())

    def test_change_view(self):
        # Get the `change_view`.
        response = self.client.get(self.get_change_url())
        self.assertEqual(response.status_code, 200)

        # Check the form action.
        form_action = re.search(
            '<form enctype="multipart/form-data" action="(.*?)" method="post" id="user_form".*?>',
            force_text(response.content)
        )
        self.assertURLEqual(form_action.group(1), '?%s' % self.get_preserved_filters_querystring())

        # Check the history link.
        history_link = re.search(
            '<a href="(.*?)" class="historylink">History</a>',
            force_text(response.content)
        )
        self.assertURLEqual(history_link.group(1), self.get_history_url())

        # Check the delete link.
        delete_link = re.search(
            '<a href="(.*?)" class="deletelink">Delete</a>',
            force_text(response.content)
        )
        self.assertURLEqual(delete_link.group(1), self.get_delete_url())

        # Test redirect on "Save".
        post_data = {
            'username': 'joepublic',
            'last_login_0': '2007-05-30',
            'last_login_1': '13:20:10',
            'date_joined_0': '2007-05-30',
            'date_joined_1': '13:20:10',
        }

        post_data['_save'] = 1
        response = self.client.post(self.get_change_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_changelist_url()
        )
        post_data.pop('_save')

        # Test redirect on "Save and continue".
        post_data['_continue'] = 1
        response = self.client.post(self.get_change_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_change_url()
        )
        post_data.pop('_continue')

        # Test redirect on "Save and add new".
        post_data['_addanother'] = 1
        response = self.client.post(self.get_change_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_add_url()
        )
        post_data.pop('_addanother')

    def test_add_view(self):
        # Get the `add_view`.
        response = self.client.get(self.get_add_url())
        self.assertEqual(response.status_code, 200)

        # Check the form action.
        form_action = re.search(
            '<form enctype="multipart/form-data" action="(.*?)" method="post" id="user_form".*?>',
            force_text(response.content)
        )
        self.assertURLEqual(form_action.group(1), '?%s' % self.get_preserved_filters_querystring())

        post_data = {
            'username': 'dummy',
            'password1': 'test',
            'password2': 'test',
        }

        # Test redirect on "Save".
        post_data['_save'] = 1
        response = self.client.post(self.get_add_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_change_url(User.objects.latest('pk').pk)
        )
        post_data.pop('_save')

        # Test redirect on "Save and continue".
        post_data['username'] = 'dummy2'
        post_data['_continue'] = 1
        response = self.client.post(self.get_add_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_change_url(User.objects.latest('pk').pk)
        )
        post_data.pop('_continue')

        # Test redirect on "Save and add new".
        post_data['username'] = 'dummy3'
        post_data['_addanother'] = 1
        response = self.client.post(self.get_add_url(), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_add_url()
        )
        post_data.pop('_addanother')

    def test_delete_view(self):
        # Test redirect on "Delete".
        response = self.client.post(self.get_delete_url(), {'post': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertURLEqual(
            response.url,
            self.get_changelist_url()
        )

    def test_url_prefix(self):
        context = {
            'preserved_filters': self.get_preserved_filters_querystring(),
            'opts': User._meta,
        }

        url = reverse('admin:auth_user_changelist', current_app=self.admin_site.name)
        self.assertURLEqual(
            self.get_changelist_url(),
            add_preserved_filters(context, url),
        )

        original_prefix = get_script_prefix()
        try:
            set_script_prefix('/prefix/')
            url = reverse('admin:auth_user_changelist', current_app=self.admin_site.name)
            self.assertURLEqual(
                self.get_changelist_url(),
                add_preserved_filters(context, url),
            )
        finally:
            set_script_prefix(original_prefix)


class NamespacedAdminKeepChangeListFiltersTests(AdminKeepChangeListFiltersTests):
    admin_site = site2


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class TestLabelVisibility(TestCase):
    """ #11277 -Labels of hidden fields in admin were not hidden. """

    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_all_fields_visible(self):
        response = self.client.get(reverse('admin:admin_views_emptymodelvisible_add'))
        self.assert_fieldline_visible(response)
        self.assert_field_visible(response, 'first')
        self.assert_field_visible(response, 'second')

    def test_all_fields_hidden(self):
        response = self.client.get(reverse('admin:admin_views_emptymodelhidden_add'))
        self.assert_fieldline_hidden(response)
        self.assert_field_hidden(response, 'first')
        self.assert_field_hidden(response, 'second')

    def test_mixin(self):
        response = self.client.get(reverse('admin:admin_views_emptymodelmixin_add'))
        self.assert_fieldline_visible(response)
        self.assert_field_hidden(response, 'first')
        self.assert_field_visible(response, 'second')

    def assert_field_visible(self, response, field_name):
        self.assertContains(response, '<div class="field-box field-%s">' % field_name)

    def assert_field_hidden(self, response, field_name):
        self.assertContains(response, '<div class="field-box field-%s hidden">' % field_name)

    def assert_fieldline_visible(self, response):
        self.assertContains(response, '<div class="form-row field-first field-second">')

    def assert_fieldline_hidden(self, response):
        self.assertContains(response, '<div class="form-row hidden')


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class AdminViewOnSiteTests(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-restaurants.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_add_view_form_and_formsets_run_validation(self):
        """
        Issue #20522
        Verifying that if the parent form fails validation, the inlines also
        run validation even if validation is contingent on parent form data
        """
        # The form validation should fail because 'some_required_info' is
        # not included on the parent form, and the family_name of the parent
        # does not match that of the child
        post_data = {"family_name": "Test1",
                     "dependentchild_set-TOTAL_FORMS": "1",
                     "dependentchild_set-INITIAL_FORMS": "0",
                     "dependentchild_set-MAX_NUM_FORMS": "1",
                     "dependentchild_set-0-id": "",
                     "dependentchild_set-0-parent": "",
                     "dependentchild_set-0-family_name": "Test2"}
        response = self.client.post(reverse('admin:admin_views_parentwithdependentchildren_add'),
                                    post_data)

        # just verifying the parent form failed validation, as expected --
        # this isn't the regression test
        self.assertIn('some_required_info', response.context['adminform'].form.errors)

        # actual regression test
        for error_set in response.context['inline_admin_formset'].formset.errors:
            self.assertEqual(['Children must share a family name with their parents in this contrived test case'],
                             error_set.get('__all__'))

    def test_change_view_form_and_formsets_run_validation(self):
        """
        Issue #20522
        Verifying that if the parent form fails validation, the inlines also
        run validation even if validation is contingent on parent form data
        """
        pwdc = ParentWithDependentChildren.objects.create(some_required_info=6,
                                                          family_name="Test1")
        # The form validation should fail because 'some_required_info' is
        # not included on the parent form, and the family_name of the parent
        # does not match that of the child
        post_data = {"family_name": "Test2",
                     "dependentchild_set-TOTAL_FORMS": "1",
                     "dependentchild_set-INITIAL_FORMS": "0",
                     "dependentchild_set-MAX_NUM_FORMS": "1",
                     "dependentchild_set-0-id": "",
                     "dependentchild_set-0-parent": str(pwdc.id),
                     "dependentchild_set-0-family_name": "Test1"}
        response = self.client.post(
            reverse('admin:admin_views_parentwithdependentchildren_change', args=(pwdc.id,)), post_data
        )

        # just verifying the parent form failed validation, as expected --
        # this isn't the regression test
        self.assertIn('some_required_info', response.context['adminform'].form.errors)

        # actual regression test
        for error_set in response.context['inline_admin_formset'].formset.errors:
            self.assertEqual(['Children must share a family name with their parents in this contrived test case'],
                             error_set.get('__all__'))

    def test_check(self):
        "Ensure that the view_on_site value is either a boolean or a callable"
        try:
            CityAdmin.view_on_site = True
            self.assertEqual(CityAdmin.check(City), [])
            CityAdmin.view_on_site = False
            self.assertEqual(CityAdmin.check(City), [])
            CityAdmin.view_on_site = lambda obj: obj.get_absolute_url()
            self.assertEqual(CityAdmin.check(City), [])
            CityAdmin.view_on_site = []
            self.assertEqual(CityAdmin.check(City), [
                Error(
                    "The value of 'view_on_site' must be a callable or a boolean value.",
                    hint=None,
                    obj=CityAdmin,
                    id='admin.E025',
                ),
            ])
        finally:
            # Restore the original values for the benefit of other tests.
            CityAdmin.view_on_site = True

    def test_false(self):
        "Ensure that the 'View on site' button is not displayed if view_on_site is False"
        response = self.client.get(reverse('admin:admin_views_restaurant_change', args=(1,)))
        content_type_pk = ContentType.objects.get_for_model(Restaurant).pk
        self.assertNotContains(response, reverse('admin:view_on_site', args=(content_type_pk, 1)))

    def test_true(self):
        "Ensure that the default behavior is followed if view_on_site is True"
        response = self.client.get(reverse('admin:admin_views_city_change', args=(1,)))
        content_type_pk = ContentType.objects.get_for_model(City).pk
        self.assertContains(response, reverse('admin:view_on_site', args=(content_type_pk, 1)))

    def test_callable(self):
        "Ensure that the right link is displayed if view_on_site is a callable"
        response = self.client.get(reverse('admin:admin_views_worker_change', args=(1,)))
        worker = Worker.objects.get(pk=1)
        self.assertContains(response, '"/worker/%s/%s/"' % (worker.surname, worker.name))

    def test_missing_get_absolute_url(self):
        "Ensure None is returned if model doesn't have get_absolute_url"
        model_admin = ModelAdmin(Worker, None)
        self.assertIsNone(model_admin.get_view_on_site_url(Worker()))


@override_settings(PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls")
class InlineAdminViewOnSiteTest(TestCase):
    fixtures = ['admin-views-users.xml', 'admin-views-restaurants.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_false(self):
        "Ensure that the 'View on site' button is not displayed if view_on_site is False"
        response = self.client.get(reverse('admin:admin_views_state_change', args=(1,)))
        content_type_pk = ContentType.objects.get_for_model(City).pk
        self.assertNotContains(response, reverse('admin:view_on_site', args=(content_type_pk, 1)))

    def test_true(self):
        "Ensure that the 'View on site' button is displayed if view_on_site is True"
        response = self.client.get(reverse('admin:admin_views_city_change', args=(1,)))
        content_type_pk = ContentType.objects.get_for_model(Restaurant).pk
        self.assertContains(response, reverse('admin:view_on_site', args=(content_type_pk, 1)))

    def test_callable(self):
        "Ensure that the right link is displayed if view_on_site is a callable"
        response = self.client.get(reverse('admin:admin_views_restaurant_change', args=(1,)))
        worker = Worker.objects.get(pk=1)
        self.assertContains(response, '"/worker_inline/%s/%s/"' % (worker.surname, worker.name))


class AdminGenericRelationTests(TestCase):
    def test_generic_relation_fk_list_filter(self):
        """
        Validates a model with a generic relation to a model with
        a foreign key can specify the generic+fk relationship
        path as a list_filter. See trac #21428.
        """
        class GenericFKAdmin(ModelAdmin):
            list_filter = ('tags__content_type',)

        validator = ModelAdminValidator()
        try:
            validator.validate_list_filter(GenericFKAdmin, Plot)
        except ImproperlyConfigured:
            self.fail("Couldn't validate a GenericRelation -> FK path in ModelAdmin.list_filter")


@override_settings(ROOT_URLCONF="admin_views.urls")
class TestEtagWithAdminView(TestCase):
    # See https://code.djangoproject.com/ticket/16003

    def test_admin(self):
        with self.settings(USE_ETAGS=False):
            response = self.client.get(reverse('admin:index'))
            self.assertEqual(response.status_code, 302)
            self.assertFalse(response.has_header('ETag'))

        with self.settings(USE_ETAGS=True):
            response = self.client.get(reverse('admin:index'))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.has_header('ETag'))


@override_settings(
    PASSWORD_HASHERS=('django.contrib.auth.hashers.SHA1PasswordHasher',),
    ROOT_URLCONF="admin_views.urls",
)
class GetFormsetsWithInlinesArgumentTest(TestCase):
    """
    #23934 - When adding a new model instance in the admin, the 'obj' argument
    of get_formsets_with_inlines() should be None. When changing, it should be
    equal to the existing model instance.
    The GetFormsetsArgumentCheckingAdmin ModelAdmin throws an exception
    if obj is not None during add_view or obj is None during change_view.
    """
    fixtures = ['admin-views-users.xml']

    def setUp(self):
        self.client.login(username='super', password='secret')

    def test_explicitly_provided_pk(self):
        post_data = {'name': '1'}
        response = self.client.post(reverse('admin:admin_views_explicitlyprovidedpk_add'), post_data)
        self.assertEqual(response.status_code, 302)

        post_data = {'name': '2'}
        response = self.client.post(reverse('admin:admin_views_explicitlyprovidedpk_change', args=(1,)), post_data)
        self.assertEqual(response.status_code, 302)

    def test_implicitly_generated_pk(self):
        post_data = {'name': '1'}
        response = self.client.post(reverse('admin:admin_views_implicitlygeneratedpk_add'), post_data)
        self.assertEqual(response.status_code, 302)

        post_data = {'name': '2'}
        response = self.client.post(reverse('admin:admin_views_implicitlygeneratedpk_change', args=(1,)), post_data)
        self.assertEqual(response.status_code, 302)
