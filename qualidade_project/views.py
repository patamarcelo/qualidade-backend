from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

from django.views.generic import TemplateView, View

from django.contrib.auth import logout
from django.shortcuts import redirect


from django.views.generic import ListView, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView

from django.contrib.auth.mixins import LoginRequiredMixin

from diamante.models import Talhao


class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, created = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user_id": user.pk,
                "email": user.email,
                "first_name": user.first_name.title(),
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "last_name": user.last_name.title(),
                "api_key": user.api_key,
                "api_secret": user.api_secret,
            }
        )


class IndexView(TemplateView):
    template_name = "home/index.html"


class LogoutView(View):
    template_name = "index.html"

    def get(self, request):
        logout(request)
        return redirect("index")


class TalhoesView(LoginRequiredMixin, TemplateView):
    login_url = "login"
    template_name = "talhao.html"
    queryset = Talhao.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["talhao"] = Talhao.objects.all()
        return context
