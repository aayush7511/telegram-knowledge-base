# FalkorDB VM (v2 knowledge graph)

FalkorDB runs in Docker on a free-tier GCE e2-micro, reached by Cloud Run over
Direct VPC egress on the VM's internal IP. Decisions and reasoning:
[docs/design/v2.md](../../docs/design/v2.md) → *Infrastructure*.

| | |
|---|---|
| Project / zone | `kb-orchestrator-8yuto1` / `us-central1-a` |
| Instance | `falkordb` — e2-micro, Container-Optimized OS (`cos-stable`), 30 GB `pd-standard` boot disk, `--no-boot-disk-auto-delete` |
| Internal IP | `10.128.0.2` (Cloud Run's `FALKORDB_HOST`); external IP only for outbound pulls/updates |
| Port 6379 | reachable from inside the VPC only (`default-allow-internal`); nothing opens it to the internet |
| Image | `falkordb/falkordb@sha256:adbddd41…` — the digest the M0 spike ran against (graph module 42004) |
| Data | `/mnt/stateful_partition/falkordb` → container `/var/lib/falkordb/data`; `--appendonly yes --save 300 1` |
| Password | `FALKORDB_PASSWORD` in `services/orchestrator/.dev.vars` (gitignored); on the VM it lives only in the systemd unit |
| Graph | `second-brain` — Graphiti's `group_id` and the FalkorDB graph key are the same value |

## Create (one-time, done 2026-09-17)

`cloud-init.yaml` is a template: render it with the password, create the VM
with it as `user-data`, then delete the rendered copy — it must never be
committed.

```bash
PW=$(grep -E '^FALKORDB_PASSWORD=' ../../services/orchestrator/.dev.vars | cut -d= -f2-)
sed "s|__FALKORDB_PASSWORD__|$PW|g" cloud-init.yaml > /tmp/cloud-init.rendered.yaml
gcloud compute instances create falkordb \
  --project=kb-orchestrator-8yuto1 --zone=us-central1-a --machine-type=e2-micro \
  --image-family=cos-stable --image-project=cos-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard --no-boot-disk-auto-delete \
  --network=default --subnet=default --tags=falkordb \
  --metadata-from-file=user-data=/tmp/cloud-init.rendered.yaml
rm /tmp/cloud-init.rendered.yaml
```

The unit runs at every boot (`--restart` semantics come from systemd
`Restart=always`), so a reboot or crash brings FalkorDB back on its own.

## Verify

```bash
gcloud compute ssh falkordb --zone us-central1-a --command '
  sudo systemctl is-active falkordb
  docker ps --format "{{.Names}} {{.Status}}"
  PW=$(grep -o "requirepass [^ ]*" /etc/systemd/system/falkordb.service | cut -d" " -f2)
  docker exec falkordb redis-cli --no-auth-warning -a "$PW" PING
  docker exec falkordb redis-cli --no-auth-warning -a "$PW" GRAPH.LIST
  free -m | head -2'
```

From outside the VPC, `nc -z <external ip> 6379` must fail.

## Look at the graph

```bash
gcloud compute ssh falkordb --zone us-central1-a --command '
  PW=$(grep -o "requirepass [^ ]*" /etc/systemd/system/falkordb.service | cut -d" " -f2)
  docker exec falkordb redis-cli --no-auth-warning -a "$PW" GRAPH.RO_QUERY second-brain \
    "MATCH (e:Episodic) RETURN e.name, e.valid_at ORDER BY e.valid_at DESC LIMIT 10"'
```

## Budget

A $1 budget on the billing account with alerts at 1% (= $0.01) of current and
forecasted spend — the "$0/month" tripwire. (gcloud stored a literal
`0.01USD` budget as one nano-dollar, hence $1 × 1%.)
