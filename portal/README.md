# Private Shaneathon portal

Static portal for shaneathon.com, with project links in `links.json`.
Build locally with `python3 portal/build.py --out /tmp/shaneathon-portal`.
The generated files do not implement authentication. Production must protect
every content request at Nginx with HTTP Basic authentication over HTTPS.
No password or hash belongs in this repository or generated HTML.

Deployment must first verify apex DNS and existing Nginx hosts so an existing
root-domain site is not replaced. Use a dedicated static root and private
server-side password file readable by the Nginx worker, outside the web root.
HTTP should serve only certificate challenges and redirects, never portal
content. HTTPS must authenticate HTML, CSS and any future private files;
disable caching and directory listings, and verify unauthenticated requests
return 401 before marking the portal ready. Add no credentials to app links.

The individual dashboards retain their existing public access settings.
Adding password protection to this portal does not change their access rules.
The user wants to set the password privately on the droplet, never in chat.

Run `python3 portal/install.py` as root in the DigitalOcean console only after
the apex A record exclusively points to the droplet. The installer checks DNS
and existing hosts before prompting on `/dev/tty` for a username (default shane)
and password twice. It uses OpenSSL SHA-512 crypt over stdin; credentials are
never command arguments. The private hash lives outside the web root, readable
only by root and the Nginx worker group. An initial HTTP host serves certificate
challenges and redirects only; the portal is never served over plain HTTP.
Certbot webroot mode sets up automatic renewal without touching other hosts.
After HTTPS setup, the installer verifies unauthenticated HTML/CSS and a wrong
password return 401 and the correct login returns 200. Existing paths cause a
safe refusal: inspect partial installations before retrying, do not erase hashes.

If the recursive resolver is stale, both authoritative Squarespace servers
must independently return the droplet's IPv4 and no IPv6 before setup proceeds.
Public ACME validation still occurs normally. Post-install portal checks connect
to local Nginx while retaining the real hostname, TLS SNI and CA verification;
no system resolver or hosts-file settings are changed. Users may still see the
old site until their own recursive caches expire.

Future private link edits belong in `/etc/shaneathon-portal-links.json` on the
server, not in public repository commits. Regenerate the static files as root
and retain their root/Nginx group ownership and restrictive file permissions.
