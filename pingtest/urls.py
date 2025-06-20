"""Define os URL patterns de pingtest."""

from django.urls import include, path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'pingtest'

urlpatterns = [
    path('', views.index, name='index'),
    path('refresh-results/', views.refresh_results, name='refresh_results'), 
    path('falha/', views.falha, name='falha'),
    path('partial-falha/', views.partial_falha, name='partial_falha'), 
    path('teste-individual/<str:test_name>/', views.teste_individual, name='teste_individual'),
    path('partial-individual/<str:test_name>/', views.partial_individual, name='partial_individual'),
    path('cadastrar-teste/', views.cadastrar_teste, name='cadastrar_teste'),
    path('editar-teste/', views.editar_teste, name='editar_teste'),
    path('editar-teste/<int:id>/', views.form_editar_teste, name='form_editar_teste'),
    path('deletar-teste/<int:id>/', views.deletar_teste, name='deletar_teste'),
    ]