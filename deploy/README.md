# Linux deployment

Production mode runs the deterministic routing review workspace. It reads a published local CSV release and records review outcomes in a local SQLite database. The service listens on loopback. Use an authenticated SSH tunnel for operator access or integrate a separately managed, authenticated HTTPS reverse proxy before offering shared access.

## Stage the application

Install Python 3.10 or later and create a dedicated system account and group named `message-routing`. Install the extracted project in `/opt/message-routing`, owned by the deployment administrator. Build the virtual environment from `requirements.txt` using your approved package source.

```bash
cd /opt/message-routing
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v
```

Before deploying, review the pinned Streamlit version and resolve and scan transitive dependencies according to your organization's package policy. The supplied service targets Linux and systemd. Test it on the target host before enabling shared access. [systemd execution environment reference](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)

## Release routing data

Create `/srv/message-routing` owned by the deployment operator and readable by group `message-routing`. Keep the release directory writable only by the deployment operator. Use set-group-ID on that shared directory so released files inherit the service group on Linux.

Convert internal extracts to the documented normalized CSV schema before publishing. Place both extracts from the same intended snapshot in a staging directory. Optional ARTRULES may be omitted. Give the service account traversal access to the release directory and read access to its data. For example, an operator with access to the staging folder can run:

```bash
cd /opt/message-routing
umask 027
.venv/bin/python -m routing_operations publish /path/to/staged-csv /srv/message-routing
```

This validates the files, writes a revision directory with a checksum manifest and atomically switches `current`. Existing revisions stay available for audit and rollback. Publish from a stable staging export. Coordinate activation through one release operator, because the latest successful activation wins. To roll back, run the same publish command with the previous `/srv/message-routing/releases/<revision>` as the source. Do not edit files in place.

## Start and check the service

```bash
sudo install -m 0644 deploy/message-routing.service /etc/systemd/system/message-routing.service
sudo systemctl daemon-reload
sudo systemctl enable --now message-routing.service
sudo systemctl status message-routing.service
sudo journalctl -u message-routing.service -n 50
```

The service runs a data and audit write-readiness check before starting. In the app, verify that the displayed revision matches the intended release. Use a test change reference to check that a blocked review has a source line and an audit ID. Check an allowed review for a draft download with the same revision and audit ID. Deploy first on synthetic data.

## Audit and recovery

SQLite stores UTC timestamps, a revision, review ID, submitted proposal, change or BRD reference, comment and the validation outcome. Blocked entries record conflict types and physical line numbers. Successful entries record the draft. The app exposes a production review result only after the audit insert commits. References and comments are stored as entered. Keep operational credentials and unrelated sensitive details out of comments.

The review database is at `/var/lib/message-routing/reviews.sqlite3`. Restrict its permissions and include it in encrypted backups using the SQLite backup API or a consistent offline copy. Retain the corresponding release directories so old line numbers can be resolved. Test restoration by running the production readiness check against the restored revision and database.

This deployment uses one application instance with a local audit database. Application-level user identity and tamper-evident audit storage are outside this release. A shared deployment that requires named reviewers, role separation or audit retention enforcement must integrate those controls. The review ID records a validation event. Draft approval and deployment belong to the existing change workflow.
