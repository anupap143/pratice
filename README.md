# practice-app

A small Python (Flask) web app for practising the full path **code → Docker image → Jenkins pipeline → Kubernetes**, built for the kind cluster `mycluster` on test-pgsql (172.16.30.124).

The page shows which pod answered your request, the node it runs on, the version Jenkins deployed, and a message and colour that come from a ConfigMap. Every one of those is something you can change and watch update.

## What's in the project

```
practice-app/
├── app/
│   ├── app.py              the web app (/, /api/info, /healthz, /readyz)
│   └── templates/index.html
├── tests/test_app.py       unit tests (pytest)
├── requirements.txt        runtime packages
├── requirements-dev.txt    test packages
├── Dockerfile              3 stages: base → test → runtime
├── Jenkinsfile             the pipeline
└── k8s/
    ├── namespace.yaml      namespace "practice"
    ├── configmap.yaml      message, colour, environment name
    ├── deployment.yaml     2 replicas, probes, resource limits, rolling update
    ├── service.yaml        ClusterIP on port 80
    └── ingress.yaml        optional, applied only if ingress-nginx is installed
```

The pipeline stages are: check tools, run unit tests, build the image, load it into kind, deploy (with automatic rollback if the rollout fails), and smoke-test from inside the cluster.

---

## Step 1: Prepare Jenkins (one time, on the server)

Skip this if your Jenkins container already has `docker`, `kind` and `kubectl`, and `/var/jenkins_home/kubeconfig` exists.

```bash
# Build a Jenkins image that contains the server's own docker, buildx, kind and kubectl
mkdir -p ~/jenkins-custom && cd ~/jenkins-custom
cp $(which docker) $(which kind) $(which kubectl) .
cp /usr/libexec/docker/cli-plugins/docker-buildx .

cat > Dockerfile <<'EOF'
FROM jenkins/jenkins:lts-jdk17
USER root
COPY docker kind kubectl /usr/local/bin/
COPY docker-buildx /usr/libexec/docker/cli-plugins/docker-buildx
RUN chmod +x /usr/local/bin/* /usr/libexec/docker/cli-plugins/docker-buildx
EOF
docker build -t my-jenkins .

# Replace the Jenkins container (jobs and settings stay in the jenkins_home volume)
docker stop jenkins && docker rm jenkins
docker run -d --name jenkins --restart unless-stopped \
  -u root \
  --memory 1536m --memory-swap 2g \
  -e JAVA_OPTS="-Xmx768m" \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network kind \
  my-jenkins

# Give Jenkins access to the cluster
kind get kubeconfig --internal --name mycluster > /tmp/kubeconfig
docker cp /tmp/kubeconfig jenkins:/var/jenkins_home/kubeconfig
rm /tmp/kubeconfig

# Check: should list mycluster-control-plane, mycluster-worker, mycluster-worker2
docker exec jenkins kubectl --kubeconfig /var/jenkins_home/kubeconfig get nodes
```

If you recreate the cluster later, run the three `kind get kubeconfig` lines again, because the cluster certificates change.

## Step 2: Try it on your PC (optional)

```powershell
cd practice-app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests        # 10 passed
python -m app.app                # then open http://localhost:8000
```

## Step 3: Push to GitHub

Create an empty repository called `practice-app` on GitHub, then:

```powershell
git init
git add .
git commit -m "practice-app: first version"
git branch -M main
git remote add origin https://github.com/<your-username>/practice-app.git
git push -u origin main
```

Never commit a kubeconfig file. `.gitignore` already excludes `*.kubeconfig`.

## Step 4: Create the Jenkins job

1. Open Jenkins through your SSH tunnel: `http://localhost:8080`
2. **New Item** → name `practice-app` → **Pipeline** → OK
3. In the **Pipeline** section:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**, Repository URL: your repo URL
   - Credentials: your GitHub username + personal access token (only if the repo is private)
   - Branch: `*/main`, Script Path: `Jenkinsfile`
4. **Save** → **Build Now** → open the build → **Console Output**

A successful build ends with `Deployed practice-app:1 to namespace practice.` and `Finished: SUCCESS`.

## Step 5: Open the app

**Option A: port-forward + SSH tunnel** (works now, because only port 22 reaches the server from your PC)

On the server:
```bash
kubectl -n practice port-forward svc/practice-app 8081:80
```
On Windows:
```powershell
ssh -L 8080:localhost:8080 -L 8081:localhost:8081 psadmin@172.16.30.124
```
Open `http://localhost:8081`.

Port-forward always talks to a single pod, so the "Send 20 requests" button will show one pod only. Use Option B or exercise 2 below to see load balancing.

**Option B: Ingress** (only useful if port 80 on 172.16.30.124 is reachable from your PC; test with `Test-NetConnection 172.16.30.124 -Port 80`)

The kind config already maps ports 80/443 to the control-plane node. Install the kind-flavoured ingress-nginx controller once:

```bash
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s
```

Run the Jenkins job again (it applies `k8s/ingress.yaml` automatically when the controller exists), then open `http://172.16.30.124/`.

---

## Practice exercises

Work through these in order. Each one teaches one Kubernetes or CI/CD idea.

**1. Change the code and redeploy.** Edit the default message in `app/app.py` or anything in `index.html`, push, and build. Watch the version number go up and the pod names change. While the build runs, watch the rolling update on the server:
```bash
kubectl -n practice get pods -w
```
Note that there are always at least 2 ready pods (`maxUnavailable: 0`).

**2. See load balancing inside the cluster.**
```bash
kubectl -n practice run looper --rm -it --restart=Never --image=curlimages/curl:8.10.1 -- \
  sh -c 'for i in $(seq 1 20); do curl -s http://practice-app/api/info | grep -o "\"pod\":\"[^\"]*\""; done'
```
The answers alternate between your pods.

**3. Change configuration without changing code.** Edit `k8s/configmap.yaml` (for example `APP_COLOR: "#7c3aed"` and a new message), push, and build. Environment variables are read only when a pod starts, so the new values appear because the build creates new pods. To apply a ConfigMap change by hand instead:
```bash
kubectl -n practice apply -f k8s/configmap.yaml
kubectl -n practice rollout restart deployment/practice-app
```

**4. Scale up and down.**
```bash
kubectl -n practice scale deployment/practice-app --replicas=4
kubectl -n practice get pods -o wide      # see the spread across mycluster-worker and mycluster-worker2
kubectl -n practice scale deployment/practice-app --replicas=2
```
The next Jenkins build sets it back to 2, because `deployment.yaml` says `replicas: 2`. That's the point of keeping configuration in Git.

**5. Self-healing.** Delete a pod and watch Kubernetes replace it:
```bash
kubectl -n practice delete pod <one-pod-name>
kubectl -n practice get pods -w
```

**6. Break a test.** Change an assertion in `tests/test_app.py` so it fails, push, and build. The pipeline stops at **Unit tests** and nothing is deployed. Fix it and push again.

**7. Break the deployment and watch the rollback.** In `k8s/deployment.yaml`, change the readiness probe path to `/does-not-exist`, push, and build. The new pods never become ready, the rollout times out after 3 minutes, and the pipeline rolls back to the previous version. The old pods keep serving the whole time. Change the path back afterwards.

**8. Roll back by hand.**
```bash
kubectl -n practice rollout history deployment/practice-app
kubectl -n practice rollout undo deployment/practice-app --to-revision=<number>
```

**9. Look inside.**
```bash
kubectl -n practice logs -l app=practice-app --tail=20     # gunicorn access log
kubectl -n practice describe pod <pod-name>               # probes, limits, events
kubectl -n practice exec -it <pod-name> -- env | grep APP_
kubectl top pods -n practice                              # needs metrics-server
```

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `kubectl: command not found` or `kind: command not found` in the console | Jenkins isn't running the custom image. Redo step 1. |
| `permission denied ... docker.sock` | The Jenkins container isn't running as root. Recreate it with `-u root`. |
| `The connection to the server ... was refused` / `no such host mycluster-control-plane` | Jenkins isn't on the `kind` network or the kubeconfig is old. Check `docker inspect jenkins --format '{{json .NetworkSettings.Networks}}'` includes `kind`, and regenerate the kubeconfig. |
| Pods stuck in `ErrImagePull` / `ImagePullBackOff` for `practice-app:N` | The image wasn't loaded into kind, or `imagePullPolicy` was changed to `Always`. Check the **Load image into kind** stage. |
| Smoke test can't pull `curlimages/curl` | Container DNS. The `daemon.json` DNS fix from the cluster README must be in place. |
| Pods `OOMKilled` | Raise `limits.memory` in `deployment.yaml` a little (the workers are capped at 1.75 GiB each). |
| `pip install` fails during the build | DNS on the server. Check `docker run --rm python:3.12-slim pip download flask -d /tmp`. |

## Clean up

```bash
kubectl delete namespace practice                 # removes everything the pipeline created
docker images 'practice-app' -q | xargs -r docker rmi -f   # old images on the server
```

Images loaded into kind also stay on the node containers. To clear old ones:
```bash
for n in mycluster-worker mycluster-worker2 mycluster-control-plane; do
  docker exec $n crictl images | grep practice-app
done
docker exec mycluster-worker crictl rmi docker.io/library/practice-app:<old-tag>
```
