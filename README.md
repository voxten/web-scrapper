### Starting
 	minikube start
	docker login
### Pushing Image
 	docker tag python-docker-web:latest voxten/python-docker-web:latest
	docker push voxten/python-docker-web:latest
	docker images
### Applying deployments for Kubernetes
	kubectl apply -f mongodb-deployment.yaml
	kubectl apply -f flaskr-deployment.yaml
### Building an app
 	docker context use default
	docker compose up --build
### Checking deployments
 	minikube dashboard
	kubectl get services
### Checking pods  
	kubectl get pods
	kubectl get po -A
