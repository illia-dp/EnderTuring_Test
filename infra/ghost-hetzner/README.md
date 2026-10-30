# Ghost on Hetzner

Один VPS: Ghost 6 + MySQL 8 + Caddy в Docker Compose. Hetzner Firewall открывает
только TCP 80/443; SSH работает через Tailscale SSH, OpenSSH отключён.
Админка доступна через Tailscale Serve; публичный `/ghost` закрыт, кроме read-only Content API.

## Запуск

Нужны Python 3.9+, подключённый Tailscale с CLI на локальном компьютере,
Hetzner Cloud API token с правами read/write и свой домен.
В Tailscale включите MagicDNS и HTTPS, создайте **одноразовый, не ephemeral,
pre-approved auth key**. Политика tailnet должна разрешать вашему пользователю
TCP 22/443 и Tailscale SSH как `root` на новом сервере. Не предоставляйте этот доступ всем участникам tailnet.

```bash
./infra/ghost-hetzner/deploy.sh --domain blog.example.com
```

Токены запрашиваются скрытым вводом, локально не сохраняются. Для автоматического
запуска можно передать `HCLOUD_TOKEN` и `TS_AUTHKEY` через окружение из менеджера
секретов; не вставляйте их в командную строку или Git.

Скрипт создаёт **платный** VPS (`cx23`, `nbg1`, Ubuntu 24.04), выводит IP и ждёт
cloud-init через Tailscale. Направьте DNS A домена на этот IP, удалите старые AAAA.
Caddy автоматически получит TLS-сертификат после обновления DNS. DNS управляется
у вашего провайдера отдельно; без него публичный HTTPS не заработает.
Параметры `--name`, `--server-type`, `--location` переопределяют значения по умолчанию.

Откройте напечатанный приватный URL `https://<server>.<tailnet>.ts.net/ghost/`
с подключённым Tailscale и создайте владельца блога.
Настройте SMTP отдельно, если нужны почта, восстановление пароля и проверка новых устройств Ghost.

## Секреты и обслуживание

Пароли БД генерируются на VPS и хранятся в `/opt/ghost/.env` с правами `0600`;
они доступны root и Docker. Hetzner API token на VPS не передаётся.
Одноразовый Tailscale key передаётся в cloud-init user-data по HTTPS; после
регистрации удаляются файл ключа и основные локальные копии user-data.
User-data доступен облачному провайдеру, поэтому используйте только одноразовый ключ;
при неудачной регистрации отзовите его. Не публикуйте cloud-init logs или Docker inspect: они могут содержать секреты.

```bash
tailscale ssh root@ghost-blog
cloud-init status --long
cd /opt/ghost && docker compose ps
docker compose logs --tail=50
```

Данные и TLS-сертификаты лежат в Docker volumes и сохраняются при перезапуске VPS.
Повторный запуск `deploy.sh` с тем же именем завершается без изменений.
При ошибке ресурсы сохраняются для диагностики: проверьте Hetzner Console и
`/var/log/cloud-init-output.log`; после исправления можно повторить
`bash /opt/ghost/bootstrap.sh` (если узел ещё не зарегистрирован, нужен новый
ключ в `/run/tailscale-auth.key`, права `0600`).
Для удаления удалите VPS и firewall `<name>-web` в Hetzner Console, а устройство —
в Tailscale. Удаление VPS уничтожит данные: резервную копию сделайте заранее.

Локальная проверка без создания ресурсов:
`python3 -m unittest discover -s infra/ghost-hetzner -p 'test_*.py'`.
