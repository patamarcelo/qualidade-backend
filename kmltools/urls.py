from django.urls import path
from .views import KMLUnionView, MeView, UsageView, CreateCheckoutSessionView, StripeWebhookView, CreateBillingPortalSessionView

urlpatterns = [
    path("kml-union/", KMLUnionView.as_view(), name="kml-union"),
    path("me/", MeView.as_view(), name="me"),
    path("usage/", UsageView.as_view(), name="usage"),
]


urlpatterns += [
    path("billing/checkout/", CreateCheckoutSessionView.as_view(), name="billing-checkout"),
    path("billing/portal/", CreateBillingPortalSessionView.as_view(), name="billing-portal"),  # NEW

]


urlpatterns += [
    path("billing/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]