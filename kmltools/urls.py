from django.urls import path
from .views import ClaimJobsView,  KMLUnionView, MeView, UsageView, CreateCheckoutSessionView, StripeWebhookView, CreateBillingPortalSessionView, KMLHistoryDownloadView, KMLHistoryView, CreatePrepaidCheckoutSessionView, KMLDownloadView, ProfileOnboardingView, UnlockFreeCreditView
from .views import SendTestReactivationEmailView, KMLJobStatusView
from .views_feedback import MergeFeedbackView
from .views_auth import RequestEmailMagicLinkView, VerifyEmailMagicLinkView

urlpatterns = [
    path("kml-union/", KMLUnionView.as_view(), name="kml-union"),
    path("me/", MeView.as_view(), name="me"),
    path("usage/", UsageView.as_view(), name="usage"),
]


urlpatterns += [
    path("billing/checkout/", CreateCheckoutSessionView.as_view(), name="billing-checkout"),
    path("billing/portal/", CreateBillingPortalSessionView.as_view(), name="billing-portal"),  # NEW
    path("billing/checkout-prepaid/", CreatePrepaidCheckoutSessionView.as_view(), name="billing-checkout-prepaid"),
    path("kml-download/<uuid:job_id>/", KMLDownloadView.as_view()),
    path("feedback/", MergeFeedbackView.as_view(), name="kmltools-feedback"),
    path("profile/onboarding/", ProfileOnboardingView.as_view(), name="profile-onboarding"),

    path("jobs/claim/", ClaimJobsView.as_view()),
    

    path("email/test-reactivation/", SendTestReactivationEmailView.as_view(), name="email_test_reactivation"),



    
    # Histórico
    path("kml/history/", KMLHistoryView.as_view(), name="kml-history"),
    path("kml/history/<uuid:job_id>/download/", KMLHistoryDownloadView.as_view(), name="kml-history-download"),
    
    path("kml/job-status/<uuid:job_id>/", KMLJobStatusView.as_view(), name="kml-job-status"),
]

urlpatterns += [
    path("billing/unlock-free-credit/", UnlockFreeCreditView.as_view(), name="unlock-free-credit"),
]


urlpatterns += [
    path("billing/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]

urlpatterns += [
    path("auth/email-link/request/", RequestEmailMagicLinkView.as_view(), name="auth-email-link-request"),
    path("auth/email-link/verify/", VerifyEmailMagicLinkView.as_view(), name="auth-email-link-verify"),
]


