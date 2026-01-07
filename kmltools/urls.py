from django.urls import path
from .views import KMLUnionView, MeView, UsageView, CreateCheckoutSessionView, StripeWebhookView

urlpatterns = [
    path("kml-union/", KMLUnionView.as_view(), name="kml-union"),
    path("me/", MeView.as_view(), name="me"),
    path("usage/", UsageView.as_view(), name="usage"),
]


urlpatterns += [
    path("billing/checkout/", CreateCheckoutSessionView.as_view(), name="billing-checkout"),
]


urlpatterns += [
    path("billing/webhook/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]