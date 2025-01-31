"""
Forms to be used in the subscriptions django app.
"""

from django import forms
from django.utils.translation import gettext as _
from durationwidget.widgets import TimeDurationWidget

from license_manager.apps.subscriptions.constants import (
    MAX_NUM_LICENSES,
    MIN_NUM_LICENSES,
    SubscriptionPlanChangeReasonChoices,
)
from license_manager.apps.subscriptions.models import (
    CustomerAgreement,
    Product,
    SubscriptionPlan,
    SubscriptionPlanRenewal,
)
from license_manager.apps.subscriptions.utils import localized_utcnow


class SubscriptionPlanForm(forms.ModelForm):
    """
    Form used for the SubscriptionPlan admin class.
    """
    # Extra form field to specify the number of licenses to be associated with the subscription plan
    num_licenses = forms.IntegerField(
        label="Number of Licenses",
        required=True,
        min_value=MIN_NUM_LICENSES,
    )

    # Using a HiddenInput widget here allows us to hide the property
    # on the creation form while still displaying the property
    # as read-only on the SubscriptionPlan update form.
    num_revocations_remaining = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )

    # Using a HiddenInput widget here allows us to hide the property
    # on the creation form while still displaying the property
    # as read-only on the SubscriptionPlan update form.
    should_auto_apply_licenses = forms.ChoiceField(
        required=False,
        widget=forms.HiddenInput()
    )

    # Extra form field to set reason for changing a subscription plan, data saved in simple history record
    change_reason = forms.ChoiceField(
        choices=SubscriptionPlanChangeReasonChoices.CHOICES,
        required=True,
        label="Reason for change",
    )

    def is_valid(self):
        # Perform original validation and return if false
        if not super().is_valid():
            return False

        # Ensure that we are getting an enterprise catalog uuid from the field itself or the linked customer agreement
        # when the subscription is first created.
        if 'customer_agreement' in self.changed_data:
            form_customer_agreement = self.cleaned_data.get('customer_agreement')
            form_enterprise_catalog_uuid = self.cleaned_data.get('enterprise_catalog_uuid')
            if not form_customer_agreement.default_enterprise_catalog_uuid and not form_enterprise_catalog_uuid:
                self.add_error(
                    'enterprise_catalog_uuid',
                    'The subscription must have an enterprise catalog uuid from itself or its customer agreement',
                )
                return False

        form_num_licenses = self.cleaned_data.get('num_licenses', 0)
        # Only internal use subscription plans to have more than the maximum number of licenses
        if form_num_licenses > MAX_NUM_LICENSES and not self.instance.for_internal_use_only:
            self.add_error(
                'num_licenses',
                f'Non-test subscriptions may not have more than {MAX_NUM_LICENSES} licenses',
            )
            return False

        # Ensure the revoke max percentage is between 0 and 100
        if self.instance.is_revocation_cap_enabled and self.instance.revoke_max_percentage > 100:
            self.add_error('revoke_max_percentage', 'Must be a valid percentage (0-100).')
            return False

        product = self.cleaned_data.get('product')

        if not product:
            self.add_error(
                'product',
                'You must specify a product.',
            )
            return False

        if product.plan_type.sf_id_required and self.cleaned_data.get('salesforce_opportunity_id') is None:
            self.add_error(
                'salesforce_opportunity_id',
                'You must specify Salesforce ID for selected product.',
            )
            return False

        return True

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class SubscriptionPlanRenewalForm(forms.ModelForm):
    """
    Form for the renewal Django admin class.
    """
    # Using a HiddenInput widget here allows us to hide the property
    # on the creation form while still displaying the property
    # as read-only on the SubscriptionPlanRenewalForm update form.
    renewed_subscription_plan = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput()
    )

    def is_valid(self):
        # Perform original validation and return if false
        if not super().is_valid():
            return False

        # Subscription dates should follow this ordering:
        # subscription start date <= subscription expiration date <= subscription renewal effective date <=
        # subscription renewal expiration date
        form_effective_date = self.cleaned_data.get('effective_date')
        form_renewed_expiration_date = self.cleaned_data.get('renewed_expiration_date')

        if form_effective_date < localized_utcnow():
            self.add_error(
                'effective_date',
                'A subscription renewal can not be scheduled to become effective in the past.',
            )
            return False

        if form_renewed_expiration_date < form_effective_date:
            self.add_error(
                'renewed_expiration_date',
                'A subscription renewal can not expire before it becomes effective.',
            )
            return False

        subscription = self.instance.prior_subscription_plan
        if form_effective_date < subscription.expiration_date:
            self.add_error(
                'effective_date',
                'A subscription renewal can not take effect before a subscription expires.',
            )
            return False

        return True

    class Meta:
        model = SubscriptionPlanRenewal
        fields = '__all__'


class CustomerAgreementAdminForm(forms.ModelForm):
    """
    Helps convert the unuseful database value, stored in microseconds,
    of ``license_duration_before_purge`` to a useful value, and vica versa.
    """

    # Hide this field when creating a new CustomerAgreement
    subscription_for_auto_applied_licenses = forms.ChoiceField(
        required=False,
        widget=forms.HiddenInput()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'instance' in kwargs:
            instance = kwargs['instance']
            if instance:
                self.populate_subscription_for_auto_applied_licenses_choices(instance)

    def populate_subscription_for_auto_applied_licenses_choices(self, instance):
        """
        Populates the choice field used to choose which plan
        is used for auto-applied licenses in a Customer Agreement.
        """
        now = localized_utcnow()
        active_plans = SubscriptionPlan.objects.filter(
            customer_agreement=instance,
            is_active=True,
            start_date__lte=now,
            expiration_date__gte=now
        )

        current_plan = instance.auto_applicable_subscription

        empty_choice = ('', '------')
        choices = [empty_choice] + [(plan.uuid, plan.title) for plan in active_plans]
        choice_field = forms.ChoiceField(
            choices=choices,
            required=False,
            initial=empty_choice if not current_plan else (current_plan.uuid, current_plan.title)
        )
        self.fields['subscription_for_auto_applied_licenses'] = choice_field

    class Meta:
        model = CustomerAgreement
        fields = '__all__'

    license_duration_before_purge = forms.DurationField(
        widget=TimeDurationWidget(
            show_days=True,
            show_hours=False,
            show_minutes=False,
            show_seconds=False,
        ),
        help_text=_(
            "The number of days after which unclaimed, revoked, or expired (due to plan expiration) licenses "
            "associated with this customer agreement will have user data retired "
            "and the license status reset to UNASSIGNED."
        ),
    )


class ProductForm(forms.ModelForm):
    """
    Form for the Product Django admin class.
    """
    class Meta:
        model = Product
        fields = '__all__'

    def is_valid(self):
        # Perform original validation and return if false
        if not super().is_valid():
            return False

        if self.instance.plan_type.ns_id_required and not self.instance.netsuite_id:
            self.add_error(
                'netsuite_id',
                'You must specify Netsuite ID for selected plan type.',
            )
            return False

        return True
