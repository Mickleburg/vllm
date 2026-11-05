# vLLM на CPU в Minikube

OpenAI-совместимый API vLLM 0.27.0 с Qwen2.5-0.5B-Instruct. Один Deployment
с rootless-контейнером vLLM и отдельным initContainer; веса сохраняются на PVC,
параметры задаются через ConfigMap, токены — через Secret. Используется Kustomize.

## Требования к окружению

Linux/amd64 с AVX2, Docker с Linux-контейнерами (Windows: Docker Desktop/WSL2),
Minikube 1.38.1, kubectl и Python 3.12+. Ни GPU, ни CUDA для запуска не нужны.
Minikube требуется 6 vCPU и 7 ГиБ RAM; освободите память от других тяжёлых
контейнеров. Образы и веса занимают несколько ГиБ диска. Первый запуск требует
доступа к Docker Hub, PyPI и Hugging Face.

Команды ниже — PowerShell из корня репозитория. Если Minikube отсутствует в PATH:

```powershell
New-Item -ItemType Directory -Force .tools | Out-Null
curl.exe -fL https://github.com/kubernetes/minikube/releases/download/v1.38.1/minikube-windows-amd64.exe -o .tools/minikube.exe
Set-Alias minikube "$PWD/.tools/minikube.exe"
```

## Запуск в Minikube

Соберите образы и создайте локальный файл с токенами:

```powershell
docker build -t vllm-cpu:local .
docker build -f Dockerfile.downloader -t vllm-downloader:local .
python scripts/new_env.py
```

`new_env.py` создаёт случайный API-ключ, а `HF_TOKEN` берёт из окружения или
оставляет пустым. Для публичной Qwen аккаунт HF и токен не нужны.
Для закрытой модели заполните HF_TOKEN в `.env` до создания Secret.
Файл исключён из Git и Docker context. При повторном запуске используйте
существующий `.env`: скрипт его не перезаписывает.

```powershell
minikube start -p vllm-test --driver=docker --cpus=6 --memory=7168 --kubernetes-version=v1.35.0
minikube -p vllm-test image load vllm-cpu:local
minikube -p vllm-test image load vllm-downloader:local
kubectl --context=vllm-test apply -f k8s/namespace.yaml
kubectl --context=vllm-test -n vllm create secret generic vllm-secrets --from-env-file=.env
kubectl --context=vllm-test apply -k k8s
kubectl --context=vllm-test -n vllm rollout status deployment/vllm --timeout=900s
kubectl --context=vllm-test -n vllm port-forward service/vllm 8000:8000 --address=127.0.0.1
```

Создание Secret рассчитано на первый запуск; существующий ресурс повторно
создавать не нужно. Оставьте `port-forward` работающим и откройте второй терминал.
У образов задан `imagePullPolicy: Never`: обе команды `image load` обязательны,
а имена собранных образов должны совпадать с манифестом.

Контекст, батч и dtype меняются в `k8s/config.yaml`; модель, HF commit SHA,
число потоков и KV cache — в `k8s/kustomization.yaml`. После изменения снова
выполните `kubectl --context=vllm-test apply -k k8s` и дождитесь rollout.
Хэш ConfigMap запускает обновление Pod без пересборки образа.
Для другой модели/ревизии нужен новый PVC; изменение Secret требует перезапуска Pod.

## Проверка API и безопасности

Во втором терминале прочитайте API-ключ из локального `.env`:

```powershell
$env:VLLM_API_KEY = (Get-Content .env | Where-Object { $_.StartsWith('VLLM_API_KEY=') }).Substring(13)
python scripts/smoke_test.py
$body = @{model='qwen-cpu'; messages=@(@{role='user'; content='What is 2 + 2?'}); max_tokens=32; temperature=0} | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8000/v1/chat/completions -Method Post -Headers @{Authorization="Bearer $env:VLLM_API_KEY"} -ContentType 'application/json' -Body $body -TimeoutSec 600
```

Smoke-тест ожидает 401 без токена и с неверным токеном, 404 для неизвестной модели,
затем 200 и непустой ответ с правильным Bearer-токеном. Тестовый маркер и ответ
печатаются только клиентом, чтобы их можно было сопоставить с серверными логами.

Rootless и отсутствие тестовых текстов/токена в журнале:

```powershell
python -m unittest discover -s tests -v
kubectl --context=vllm-test -n vllm exec deployment/vllm -c vllm -- id
New-Item -ItemType Directory -Force artifacts | Out-Null
python scripts/smoke_test.py | Out-File artifacts/k8s-smoke.json -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Smoke test failed' }
kubectl --context=vllm-test -n vllm logs deployment/vllm -c vllm 2>&1 | Out-File artifacts/k8s-server.log -Encoding utf8
python scripts/check_logs.py artifacts/k8s-smoke.json artifacts/k8s-server.log
```

Ожидается UID/GID 10001. В серверном логе остаются `http_request` с маршрутом
и статусом, без промпта, ответа и Bearer-токена. `artifacts/` исключён из Git.
Штатный RequestLogger отключён, сообщения обрабатывает metadata-only форматтер.
Pod использует `runAsNonRoot`, `readOnlyRootFilesystem`, запрет повышения
привилегий и `drop: ALL`. HF-токен получает только initContainer, API-ключ —
только vLLM; значения не нужно подставлять в команды вручную.

Для проверки повторного использования PVC отдельно пересоздайте Pod:

```powershell
kubectl --context=vllm-test -n vllm logs deployment/vllm -c download-model
kubectl --context=vllm-test -n vllm rollout restart deployment/vllm
kubectl --context=vllm-test -n vllm rollout status deployment/vllm --timeout=900s
kubectl --context=vllm-test -n vllm logs deployment/vllm -c download-model
```

При первой загрузке ожидается `model_download_complete`, после рестарта —
`model_cache_hit`. vLLM читает локальные веса с offline-флагами HF.
После замены Pod завершите прежний `port-forward` через Ctrl+C и заново
запустите переадресацию из раздела запуска перед следующими запросами.

## Нагрузочный тест

При работающем `port-forward` и заданном `$env:VLLM_API_KEY`:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null
python scripts/benchmark.py --requests 4 --concurrency 2 --max-tokens 32 | Out-File artifacts/benchmark.json -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed' }
```

Результаты от 05.11.2026: Intel i5-13500H, Minikube 6 vCPU / 7 ГиБ,
float32, 4 OpenMP-потока, KV cache 1 ГиБ, контекст и token budget 2048,
`max-num-seqs=4`. На каждый размер — 4 запроса с конкурентностью 2,
выход фиксирован в 32 токена. Один запрос прогрева исключён; уникальные
префиксы предотвращают повторное использование prefix cache между запросами.

| Вход | Входных токенов | Выходных токенов | TTFT p50, с | E2E p50, с | Выходных токенов/с | Запросов/с |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Короткий | 67 | 32 | 0,80 | 5,54 | 11,55 | 0,361 |
| Длинный | 1034 | 32 | 5,88 | 11,87 | 5,37 | 0,168 |

Токены берутся из `usage`. TTFT измеряется до первого непустого content delta,
E2E — до `[DONE]`, throughput — выходные токены / время всей серии.
Исходные данные: [benchmark-results.json](docs/benchmark-results.json).
Выборка мала; предел нагрузки и хвостовые задержки по ней не определяются.

Для коротких запросов стоит подбирать `max-num-seqs` и размер батча, учитывая
очередь и RAM. Для длинных — согласовать контекст, KV cache и конкурентность,
затем сравнить token budget и chunked prefill. Это гипотезы для дальнейших
измерений: в текущей серии конфигурации между собой не сравнивались.

## Ограничения и подробности

Основной образ занимает около 7,45 ГБ, загрузчик - 238 МБ в распакованном виде.
Холодный старт и первая JIT-компиляция Triton CPU могут занимать минуты,
в том числе после готовности `/health`; таймаут smoke-теста — 600 секунд.
Запас RAM небольшой, качество модели 0.5B ограничено. Проверены Linux/amd64 и AVX2.

Оба образа закреплены по digest, все Python-зависимости - по версиям.
Rootless относится к процессам контейнеров. Secret не заменяет шифрование etcd;
TLS/Ingress не настроены, `/health` открыт для probes. Приватная модель
с реальным HF-токеном не тестировалась.

Остановить Minikube без удаления PVC: `minikube stop -p vllm-test`.
Для сохранения весов не используйте `minikube delete`.

Источники: [vLLM CPU](https://docs.vllm.ai/en/v0.27.0/getting_started/installation/cpu/),
[логирование](https://github.com/vllm-project/vllm/blob/v0.27.0/examples/features/logging_configuration.md),
[модель Qwen](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct).
