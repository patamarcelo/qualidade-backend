from django.urls import path
from .views import KMLUnionView, MeView, UsageView, CreateCheckoutSessionView, StripeWebhookView, CreateBillingPortalSessionView, KMLHistoryDownloadView, KMLHistoryView

urlpatterns = [
    path("kml-union/", KMLUnionView.as_view(), name="kml-union"),
    path("me/", MeView.as_view(), name="me"),
    path("usage/", UsageView.as_view(), name="usage"),
]


urlpatterns += [
    path("billing/checkout/", CreateCheckoutSessionView.as_view(), name="billing-checkout"),
    path("billing/portal/", CreateBillingPortalSessionView.as_view(), name="billing-portal"),  # NEW
    
    # Histórico
    path("kml/history/", KMLHistoryView.as_view(), name="kml-history"),
    path("kml/history/<uuid:job_id>/download/", KMLHistoryDownloadView.as_view(), name="kml-history-download"),
]


urlpatterns += [
    path("billing/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]