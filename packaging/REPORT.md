# Проверка упаковки — 2026-11-04

Добавлены `packaging/cozystack/` (tenant app, cozy-lib, ApplicationDefinition/cozyrds, dashboard schema, WorkloadMonitor, presets, tenant storage/S3, PackageSource и узкий grant для tenant-admin) и `packaging/kubepkg/` (recipe, проверки подписанного каталога/SBOM и установки через kind/operator). `prepare.py` собирает самостоятельные деревья из этого репозитория, не изменяя checkout платформ. Ревизии прочитанных платформ записаны в `platforms.lock.yaml`.

В core изменены `charts/mnemosyne/values.yaml`, `templates/addon.yaml`, `values.schema.json`, README и генератор `hack/addon/schema.py`: добавлены `rbacScope: namespace` и `manageQuota`. Значения по умолчанию сохраняют standalone-поведение. Tenant app фиксирует namespace, исключает Secrets и кластерные объекты из inventory, использует существующий PriorityClass и квоты tenant. Девять новых тестов находятся в `tests/test_packaging.py`.

## Что действительно выполнено

Все проверки выполнялись **локально**, без установки в Kubernetes:

- `helm lint` core, Cozystack app с настоящим cozy-lib из checkout и registration chart: для каждого `1 chart(s) linted, 0 chart(s) failed`. `helm template` app и регистрации с CRD — успешно. Информационное замечание Helm: рекомендована иконка.
- `test_packaging.py`: `Ran 9 tests ... OK`; `test_addon.py`: `Ran 14 tests ... OK`; `test_model_chart.py`: `Ran 2 tests ... OK`. Всего 25 тестов. Проверены оба tenant namespace, отсутствие кластерного RBAC в активном tenant core, сохранение PVC, S3 references, presets, schema и guard-проверки.
- CLI собран из `~/projects/kubepkg` с `go build -mod=readonly`, вывод — `out/packaging-final-20261104/kubepkg-current`; checkout не изменён. Go сообщил об отказе записи необязательного stat cache в `~/go/pkg/mod/cache`, но сборка завершилась с кодом 0. Готовый старый `bin/kubepkg` проверялся первым; окончательные результаты получены новым CLI.
- Новый CLI: `validate`: `out/packaging-final-20261104/kubepkg: ok`; `build`: `built mnemosyne 0.2.0 build 1 ... (not published: no --registry)`. Архив текущего CLI: `mnemosyne-0.2.0-1.tgz`.
- Локальный HTTP-каталог: проверен SHA-256 реального архива chart, создан и проверен подписанный тестовым ключом index; `PASS: signed local index, verified chart digest, CycloneDX 1.6; 2 components`. SBOM: `out/packaging-final-20261104/supply-chain-current/catalog.cdx.json`. Это пакет и chart неактивного каталога, **без образов**. Ключ находится вне обслуживаемого HTTP-каталога, сервер после проверки остановлен.
- `compileall` для packaging и `git diff --check`: код 0.

Промежуточная генерация schema сначала упала на integer в window; обработка integer исправлена, генерация и дальнейшие проверки прошли. Неудачные промежуточные каталоги в `out/` сохранены.

## Что не завершено

Попытка `kind create cluster --name mnemosyne-package-check-20261104 --kubeconfig out/packaging-check-20261104-2/kind.kubeconfig --wait 30s` завершилась с кодом 1: `failed to get docker info`, `dial unix /var/run/docker.sock: connect: no such file or directory`. Preflight альтернативы: `podman is not installed; no cluster was touched`. Кластер не создан, оператор и пакет **не установлены**. Workshop, включая его platform namespaces, не затронут; Secrets не запрашивались. Live Cozystack, PVC/S3 и dashboard не проверялись.

Реальные Actions digest controller/studio не предоставлены. `prepare.py --release` ожидаемо отказывается: `ValueError: controller: real Actions digest required`. Поэтому текущая проверенная сборка — неактивный каталог, а не готовый исполняемый релиз. Полный image SBOM, OCI-публикация и установка активного пакета остаются release gates. Поддельные digest не записаны; тестовые хеши существуют только в render fixtures теста и не используются для публикации/запуска.

Для завершения нужны Actions-образы из согласованной ревизии, owner values с ключом-ссылкой и комиссией для chamber (либо явно выбранным background с endpoints), работающий kind runtime и доступный подписанный registry/index. Художественная комиссия не сочинялась. Команды подготовки, публикации, SBOM и установки находятся в README обеих обёрток. Проверка `kind_check.py` создаёт отдельный kubeconfig, сохраняет кластер и результаты, не использует текущий context и не удаляет данные.

## Коммиты после review

Ничего не закоммичено и не отправлено. Исходники task 11 и другие пользовательские изменения уже были незакоммичены до этой работы; сначала отделить их при review. Предлагаемые логические коммиты после подготовки соответствующего staging:

```sh
git commit --signoff -m 'feat(helm): support namespace-scoped atelier deployments' -m 'Assisted-by: LLM'
git commit --signoff -m 'feat(packaging): add Cozystack and Kuberoot package wrappers' -m 'Assisted-by: LLM'
```

Первый — изменения core и его генератора; второй — `packaging/` и `tests/test_packaging.py`. Не включать `out/`, тестовые ключи и чужие изменения. PR в платформы не создавались.
