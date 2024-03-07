from django.db import models

# Create your models here.


class Base(models.Model):
    criados = models.DateTimeField("Criação", auto_now_add=True)
    modificado = models.DateTimeField("Atualização", auto_now=True)
    ativo = models.BooleanField("Ativo", default=True)
    observacao = models.TextField("Observação", blank=True, null=True)

    class Meta:
        abstract = True


# -------------  ------------- ESTRUTURA -------------  -------------#


class TecnicoAgricola(Base):
    nome = models.CharField("Nome", max_length=100, unique=True)
    crea_number = models.CharField("Numero do CREA", max_length=100, unique=True)

    class Meta:
        verbose_name = "Técnico Agrícola"
        verbose_name_plural = "Técnicos Agrícola"

    def __str__(self) -> str:
        return f"{self.nome} - {self.crea_number}"
