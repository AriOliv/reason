# deploy

Infrastructure as code. Private by default: agents have no public address, egress goes through NAT, secrets come from a secret manager, and only the gateway is exposed. The prototype runs on Google Cloud (a private ARM VM reached only through IAP); the product targets Kubernetes with one namespace per person.
