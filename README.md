### Prerequisites for Windows
#### Docker
 	https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe
#### Minikube
    https://storage.googleapis.com/minikube/releases/latest/minikube-installer.exe
### Starting
 	minikube start
	docker login
### Pushing Image
 	docker tag python-docker-web:latest <your-repository-name>/python-docker-web:latest
	docker push <your-repository-name>/python-docker-web:latest
	docker images
### Applying deployments for Kubernetes
	kubectl apply -f mongodb-deployment.yaml
	kubectl apply -f flask-deployment.yaml
### Building an app
 	docker context use default
	docker compose up --build
### Checking deployments
 	minikube dashboard
	kubectl get services
### Checking pods  
	kubectl get pods
	kubectl get po -A
