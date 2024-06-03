from flask import Flask, request, render_template, redirect, url_for
import os
from pymongo import MongoClient
import asyncio
from datetime import datetime
from pymongo.server_api import ServerApi
from concurrent.futures import ProcessPoolExecutor
import json
from github import Github
from requests.exceptions import MissingSchema
from web_scrapper import scrape

app = Flask(__name__)

mongo_host = os.getenv('MONGO_HOST', 'localhost')
mongo_port = os.getenv('MONGO_PORT', '27017')
mongo_user = os.getenv('MONGO_INITDB_ROOT_USERNAME', 'root')
mongo_pass = os.getenv('MONGO_INITDB_ROOT_PASSWORD', 'pass')
mongo_url = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"

# Load the GitHub token and repository details from environment variables
github_token = os.getenv('GITHUB_TOKEN')
github_repo_name = os.getenv('GITHUB_REPO_NAME')
github_branch_name = os.getenv('GITHUB_BRANCH_NAME')

client = MongoClient(mongo_url, server_api=ServerApi('1'))
mydb = client["Projekt"]
scraped_urls_collection = mydb["scraped_urls"]

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


def serialize_document(doc):
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/scrape', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        print("Scraping started")
        url = request.form['url']
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            data = loop.run_until_complete(scrape(url))
            print("Scraping finished")
            if data:
                return render_template('results.html', url=url, results=data)
            else:
                return render_template('failed_results.html')
        except MissingSchema:
            return render_template('invalid_url.html')

    return render_template('index.html')


@app.route('/export_to_github', methods=['POST'])
def export_to_github():
    # Print environment variables for debugging
    print(f"GitHub Token: {github_token}")
    print(f"GitHub Repo Name: {github_repo_name}")
    print(f"GitHub Branch Name: {github_branch_name}")
    g = Github(github_token)
    repo = g.get_repo(github_repo_name)
    now = datetime.now()
    branch = github_branch_name

    # Collect all data from the MongoDB
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]
    all_data = {}
    for collection_name in collections:
        collection = mydb[collection_name]
        documents = collection.find()
        all_data[collection_name] = [serialize_document(doc) for doc in documents]

    # Convert the data to JSON format
    all_data_json = json.dumps(all_data, indent=4)

    # Create a commit message
    commit_message = "Export scraped data"

    # Specify the file path in the repository
    file_path = f"data/{now.strftime('%Y-%m-%d-%H-%M-%S')}_scraped_data.json"

    # Get the file if it exists in the repository

    repo.create_file(file_path, commit_message, all_data_json, branch=branch)

    return redirect(url_for('all_data'))


@app.route('/all_data')
def all_data():
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]
    all_data = {}
    for collection_name in collections:
        collection = mydb[collection_name]
        documents = collection.find()
        all_data[collection_name] = [serialize_document(doc) for doc in documents]

    return render_template('all_data.html', all_data=all_data, collections=collections, selected_data=None,
                           selected_collection=None, selected_data_type=None)


@app.route('/view_data', methods=['POST'])
def view_data():
    collection_name = request.form['collection']
    data_type = request.form['data_type']

    collection = mydb[collection_name]
    if data_type == 'none':
        selected_data = None
    else:
        documents = collection.find({"type": data_type})
        selected_data = [serialize_document(doc) for doc in documents]

    all_data = {collection_name: [serialize_document(doc) for doc in collection.find()]}
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]

    return render_template('all_data.html', all_data=all_data, collections=collections,
                           selected_data=selected_data, selected_collection=collection_name,
                           selected_data_type=data_type)


@app.route('/delete_all', methods=['POST'])
def delete_all():
    collections = mydb.list_collection_names()
    for collection_name in collections:
        mydb[collection_name].drop()  # Drop collection
    return redirect(url_for('all_data'))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
