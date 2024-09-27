from django.db.models.signals import post_save, post_delete
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Plantio, Aplicacao,PlannerPlantio

from django.core.cache import cache
    
    
@receiver(post_save, sender=Plantio, weak=False)
@receiver(post_delete, sender=Plantio, weak=False)
def invalidate_cache_on_update(sender, instance, **kwargs):
    print('invalidando cache')
    cicle_filter = instance.ciclo.ciclo
    safra_filter = instance.safra.safra
    cache_key = f"get_plantio_operacoes_detail_json_program_qs_plantio_{instance.safra.safra}_{instance.ciclo.ciclo}"
    cache_key_qs_plantio_get_plantio_operacoes_detail = f"get_plantio_operacoes_detail_qs_plantio_{safra_filter}_{cicle_filter}"
    cache_key_qs_plantio_map = f"get_plantio_map_{safra_filter}_{cicle_filter}"
    cache_key_web = f"get_plantio_operacoes_detail_json_program_qs_plantio_web_{safra_filter}_{cicle_filter}"
    cache.delete(cache_key)  # Invalidate cache whenever Plantio model changes
    cache.delete(cache_key_web)  # Invalidate cache whenever Plantio model changes
    cache.delete(cache_key_qs_plantio_get_plantio_operacoes_detail)  # Invalidate cache whenever Plantio model changes
    cache.delete(cache_key_qs_plantio_map)  # Invalidate cache whenever Plantio model changes


@receiver(post_save, sender=PlannerPlantio, weak=False)
@receiver(post_delete, sender=PlannerPlantio, weak=False)
def invalidate_cache_on_update(sender, instance, **kwargs):
    print('invalidando cache PlannerPlantio')
    cicle_filter = instance.ciclo.ciclo
    safra_filter = instance.safra.safra
    cache_key_qs_planejamento = f"get_plantio_operacoes_detail_qs_planejamento_{safra_filter}_{cicle_filter}"
    print('cache_key:', cache_key_qs_planejamento)
    cache.delete(cache_key_qs_planejamento)  # Invalidate cache whenever Plantio model changes


@receiver(post_save, sender=Aplicacao, weak=False)
@receiver(post_delete, sender=Aplicacao, weak=False)
def invalidate_cache_on_update(sender, instance, **kwargs):
    print('invalidando cache Aplicacao')
    cicle_filter = instance.operacao.programa.ciclo.ciclo
    safra_filter = instance.operacao.programa.safra.safra
    cache_key_qs_aplicacoes = f"get_plantio_operacoes_detail_qs_aplicacoes_{safra_filter}_{cicle_filter}"
    print('cache_key:', cache_key_qs_aplicacoes)
    cache.delete(cache_key_qs_aplicacoes)  # Invalidate cache whenever Plantio model changes

