from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.fields import CurrentUserDefault

from usuario.models import CustomUsuario as User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model        = User
        # fields       = ('id', 'email','password', 'first_name', 'last_name', 'fone')
        fields       = ('id', 'email','password', 'first_name')
        # fields = '__all__'
        extra_kwargs = {'password': {'write_only': True, 'required': True}}

    def create(self,validated_data):
        user = User.objects.create_user(**validated_data)
        Token.objects.create(user=user)
        return user