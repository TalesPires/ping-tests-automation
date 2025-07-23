from django.shortcuts import redirect, render
from pingtest.models import NetworkTestResult, NetworkTestScenario
from .forms import NetworkTestScenarioForm 
from django.contrib.auth.decorators import login_required   

@login_required
def index(request):
    # Get all unique test names
    test_names = NetworkTestResult.objects.values_list('test_name', flat=True).distinct()

    cards = []
    for name in test_names:
        latest = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end').first()
        latest_failure = NetworkTestResult.objects.filter(test_name=name).exclude(success="SF").order_by('-test_end').first()
        cards.append({
            'test_name': name,
            'latest': latest,
            'latest_failure': latest_failure,
        })
        
    cards.sort(key=lambda c: c['test_name'])

    return render(request, 'index.html', {'cards': cards})

@login_required
def refresh_results(request):
    # Get all unique test names
    test_names = NetworkTestResult.objects.values_list('test_name', flat=True).distinct()

    cards = []
    for name in test_names:
        latest = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end').first()
        latest_failure = NetworkTestResult.objects.filter(test_name=name).exclude(success="SF").order_by('-test_end').first()
        cards.append({
            'test_name': name,
            'latest': latest,
            'latest_failure': latest_failure,
        })
    
    cards.sort(key=lambda c: c['test_name'])

    return render(request, 'partials/partial_index.html', {'cards': cards})

@login_required
def falha(request): 
    # Get all unique test names
    test_names = NetworkTestResult.objects.values_list('test_name', flat=True).distinct()

    cards = []
    for name in test_names:
        latest = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end').first()
        # Get the last 4 results for this test
        recent_tests = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end')[:4]
        # Check if any of the last 4 results is not "SF"
        has_failure = any(t.success != "SF" for t in recent_tests)
        latest_failure = NetworkTestResult.objects.filter(test_name=name).exclude(success="SF").order_by('-test_end').first()
        cards.append({
            'test_name': name,
            'latest': latest,
            'latest_failure': latest_failure,
            'has_failure': has_failure,
        })
    
    cards.sort(key=lambda c: c['test_name'])

    return render(request, 'falha.html', {'cards': cards})   

@login_required
def partial_falha(request): 
    # Get all unique test names
    test_names = NetworkTestResult.objects.values_list('test_name', flat=True).distinct()

    cards = []
    for name in test_names:
        latest = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end').first()
        # Get the last 4 results for this test
        recent_tests = NetworkTestResult.objects.filter(test_name=name).order_by('-test_end')[:4]
        # Check if any of the last 4 results is not "SF"
        has_failure = any(t.success != "SF" for t in recent_tests)
        latest_failure = NetworkTestResult.objects.filter(test_name=name).exclude(success="SF").order_by('-test_end').first()
        cards.append({
            'test_name': name,
            'latest': latest,
            'latest_failure': latest_failure,
            'has_failure': has_failure,
        })
        
    cards.sort(key=lambda c: c['test_name'])

    return render(request, 'partials/partial_falha.html', {'cards': cards})

@login_required
def teste_individual(request, test_name):
    testes = NetworkTestResult.objects.filter(test_name=test_name).order_by('-test_end')
    return render(request, 'teste_individual.html', {'testes': testes, 'test_name': test_name })

@login_required
def partial_individual(request, test_name):
    testes = NetworkTestResult.objects.filter(test_name=test_name).order_by('-test_end')
    return render(request, 'partials/partial_individual.html', {'testes': testes,})

@login_required
def cadastrar_teste(request): 
    show_modal = False
    if request.method != 'POST':
        form = NetworkTestScenarioForm()
    else:  
        form = NetworkTestScenarioForm(request.POST)
        if form.is_valid():
            form.save()
            show_modal = True
    
    return render(request, 'cadastrar_teste.html', {'form': form,'show_modal': show_modal,})

@login_required
def editar_teste(request):
    scenarios = NetworkTestScenario.objects.all()
    
    return render(request, 'editar_teste.html', {'scenarios': scenarios,})

@login_required
def form_editar_teste(request, id):
    scenario = NetworkTestScenario.objects.get(id=id)
    
    form = NetworkTestScenarioForm(request.POST or None,instance=scenario)
    
    if form.is_valid():
        form.save()
        return redirect('pingtest:editar_teste')  
    
    return render(request, 'form_editar_teste.html', {'form': form, 'id': id})

@login_required
def deletar_teste(request, id):  
    scenario = NetworkTestScenario.objects.get(id=id)
    scenario.delete()
    return redirect('pingtest:editar_teste')