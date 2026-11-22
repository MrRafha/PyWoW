# Guia de deploy — servidor em casa com Tailscale

Como hospedar o PyWoW numa máquina sua e jogar com amigos pela internet, sem abrir portas no roteador.

## 1. Requisitos

| | Mínimo |
|---|---|
| Máquina | Qualquer PC/notebook ligado 24h (ou só durante a jogatina) |
| RAM | 2 GB (4 GB folgado) |
| Disco | ~500 MB (o `data/world.db` tem ~60 MB) |
| SO | Linux recomendado (Ubuntu/Debian). Windows também funciona |
| Python | 3.11+ |
| Rede | Qualquer internet residencial — 5–10 jogadores usam pouquíssima banda |

Cada jogador precisa do cliente **WoW 3.3.5a, build 12340**.

## 2. Instalar o servidor

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
git clone https://github.com/MrRafha/PyWoW.git ~/pywow
cd ~/pywow
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
```

## 3. Tailscale (rede privada entre você e os amigos)

Muitos provedores no Brasil usam **CGNAT**, então redirecionar portas no roteador não funciona. O Tailscale cria uma rede virtual privada: cada amigo instala, entra na sua rede e enxerga o servidor como se estivesse na mesma casa. O servidor **não** fica exposto pra internet.

**No servidor:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4        # anote esse IP, ex.: 100.101.102.103
```

**Nos amigos:** instalar o Tailscale (Windows/macOS/Linux) em <https://tailscale.com/download> e entrar na rede. Duas formas:
- **Compartilhar a máquina** (recomendado): no painel <https://login.tailscale.com/admin/machines>, menu `...` do servidor → **Share** → mande o link. O amigo usa a própria conta e só enxerga essa máquina.
- **Convidar pra sua tailnet**: Settings → Users → Invite. Ele passa a ver todas as suas máquinas.

Teste do PC do amigo: `ping 100.101.102.103` (o IP que você anotou).

> Firewall: se o servidor usa `ufw`, libere a interface do Tailscale: `sudo ufw allow in on tailscale0`.

## 4. Configurar o servidor pro IP do Tailscale

Edite `config/config.yaml`:

```yaml
authserver:
  host: 0.0.0.0                  # escuta em todas as interfaces (127.0.0.1 só aceita conexão local)
  realm_name: "PyWoW"
  realm_address: 100.101.102.103 # IP do Tailscale — é o endereço que o cliente recebe na lista de realms

worldserver:
  host: 0.0.0.0
```

> Prefere não escutar em todas as interfaces? Use o próprio IP do Tailscale em `host` nas duas seções.

Inicialize os bancos e crie as contas (uma por amigo):

```bash
.venv/bin/python tools/init_db.py
.venv/bin/python tools/create_test_account.py RAFHA minhasenha
.venv/bin/python tools/create_test_account.py AMIGO1 senhadele
```

> O servidor é experimental — não reutilize senhas importantes.

Teste rodando na mão:
```bash
.venv/bin/python run_servers.py
```

## 5. Configurar o cliente

Na pasta do WoW de cada jogador, edite `Data/ptBR/realmlist.wtf` (ou `Data/enUS/realmlist.wtf`):

```
set realmlist 100.101.102.103
```

Abra o `Wow.exe` (não o launcher), confira **3.3.5 (12340)** no canto da tela de login e entre com a conta criada. Veja também a seção *Client setup* do [DOCUMENTATION.md](../DOCUMENTATION.md) (CVars de nameplate, addons, `tools/apply_client_settings.py`).

**Não conecta?**
- `ping` no IP do Tailscale funciona? Se não, é rede/Tailscale.
- Trava em "Connecting": `realm_address` errado ou `authserver.host` ainda em `127.0.0.1`.
- Passa do login mas trava na lista de realms/personagens: `worldserver.host` em `127.0.0.1` ou porta 8085 bloqueada no firewall.
- Logs ficam em `logs/`.

## 6. Rodar como serviço (systemd)

Pra subir junto com a máquina e reiniciar sozinho se cair. Copie o arquivo de exemplo e ajuste usuário e caminho:

```bash
sudo cp deploy/pywow.service /etc/systemd/system/pywow.service
sudo nano /etc/systemd/system/pywow.service   # troque User= e os caminhos /home/SEU_USUARIO/pywow
sudo systemctl daemon-reload
sudo systemctl enable --now pywow
```

Comandos úteis:
```bash
systemctl status pywow
journalctl -u pywow -f       # logs ao vivo
sudo systemctl restart pywow # depois de atualizar o código
```

Atualizar:
```bash
cd ~/pywow && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart pywow
```

## 7. Backup

Os dados dos jogadores (contas, personagens, inventário) ficam em `data/auth.db` e `data/world.db`. O `sqlite3 .backup` copia com segurança mesmo com o servidor rodando:

```bash
sudo apt install -y sqlite3
mkdir -p ~/pywow-backups
sqlite3 ~/pywow/data/auth.db  ".backup '$HOME/pywow-backups/auth-$(date +%F).db'"
sqlite3 ~/pywow/data/world.db ".backup '$HOME/pywow-backups/world-$(date +%F).db'"
```

Pra fazer todo dia às 4h, `crontab -e` e adicione (troque o usuário):
```
0 4 * * * sqlite3 /home/SEU_USUARIO/pywow/data/auth.db ".backup '/home/SEU_USUARIO/pywow-backups/auth-$(date +\%F).db'" && sqlite3 /home/SEU_USUARIO/pywow/data/world.db ".backup '/home/SEU_USUARIO/pywow-backups/world-$(date +\%F).db'"
```

## Windows como servidor

Também funciona: instale Python 3.11+ e o Tailscale, siga os passos 2–5 trocando `.venv/bin/python` por `.venv\Scripts\python`, e rode `run_servers.py` num terminal. Libere o Python no Firewall do Windows quando ele pedir (marque **Redes privadas**).
