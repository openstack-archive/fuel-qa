import base64
import json
import os
import urlparse

import requests

from fuelweb_test import logger


class RallydClient(object):
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.session = requests.Session()

    def log_request(self, url, method,
                    request_headers, request_body,
                    response_headers, response_body):
        log_fmt = """Request {url} {method}
    Request - Headers: {request_headers}
        Body: {request_body}
    Response - Headers: {response_headers}
        Body: {response_body}"""

        logger.info(log_fmt.format(url=url,
                                   method=method,
                                   request_headers=request_headers,
                                   request_body=request_body,
                                   response_headers=response_headers,
                                   response_body=response_body))

    def set_base_url(self, base_url):
        self.base_url = base_url

    def request(self, method, url, headers=None, body=None, **kwargs):
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        r = requests.request(method, urlparse.urljoin(self.base_url, url),
                             headers=headers, data=body, **kwargs)

        self.log_request(url=urlparse.urljoin(self.base_url, url),
                         method=method,
                         request_headers=headers,
                         request_body=body,
                         response_headers=r.headers,
                         response_body=r.content)

        return r.headers, r.content

    def post(self, url, body=None, deserialize=True, **kwargs):
        headers, body = self.request("POST", url,
                                     body=json.dumps(body),
                                     **kwargs)

        if deserialize:
            return json.loads(body)
        return body

    def get(self, url, deserialize=True, **kwargs):
        headers, body = self.request("GET", url, **kwargs)

        if deserialize:
            return json.loads(body)
        return body

    def recreate_db(self):
        return self.post("/db")

    def deployment_create(self, auth_url, username, password,
                          tenant_name, from_env):
        body = {"OS_AUTH_URL": auth_url,
                "OS_USERNAME": username,
                "OS_PASSWORD": password,
                "OS_TENANT_NAME": tenant_name}

        if from_env:
            body = dict((key, os.environ.get(key)) for key in body)

        return self.post("/deployments", body)

    def scenario_create(self, scenario_file, scenario_type,
                        name=None, filename=None):
        with file(scenario_file) as scenario:
            data = base64.b64encode(scenario.read())

        body = {"data": data,
                "type": scenario_type,
                "filename": filename,
                "name": name}

        return self.post("/scenarios", body)

    def scenarios_list(self,):
        return self.get("/scenarios")

    def task_add(self, scenario_id,):
        return self.post("/tasks", body={"scenario_id": scenario_id})

    def task_list(self):
        return self.get("/tasks")

    def task_get(self, task_id):
        return self.get("/tasks/{0}".format(task_id))

    def run_create(self, task_ids):
        return self.post("/runs", body={"task_ids": task_ids})

    def run_list(self):
        return self.get("/runs")

    def run_get(self, run_id):
        return self.get("/runs/{0}".format(run_id))

    def task_result_download(self, filename):
        return self.get("/result/{0}".format(filename),
                        deserialize=False, stream=True)

    def run_result_download(self, run_id, download_dir="."):
        results = self.get("/runs/{0}/result".format(run_id))

        for filename in results["results"]:
            content = self.task_result_download(filename)
            path = os.path.join(download_dir, os.path.split(filename)[-1])
            with open(path, "wb") as result:
                result.write(content)
                # for block in r.iter_content(1024):
                #     result.write(block)

        return results
