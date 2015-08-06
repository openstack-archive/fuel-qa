import json
import os
import urlparse

import requests

from fuelweb_test import logger


class RallydClient(object):
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.session = requests.Session()

    def set_base_url(self, base_url):
        self.base_url = base_url

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

    def request(self, url, method, headers=None, body=None, **kwargs):
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        r = requests.request(method, urlparse.urljoin(self.base_url, url),
                             headers=headers, data=body, **kwargs)

        if r.headers.get('Content-Type') == 'application/json':
            body = json.loads(r.content)
        else:
            body = r.content

        if r.status_code == 500:
            raise requests.HTTPError(r.content)

        return r.headers, body

    def post(self, url, body=None, **kwargs):
        return self.request(url, "POST", body=json.dumps(body), **kwargs)

    def get(self, url, **kwargs):
        return self.request(url, "GET", **kwargs)

    def put(self, url, body=None, **kwargs):
        return self.request(url, "PUT", body=json.dumps(body), **kwargs)

    def delete(self, url, **kwargs):
        return self.request(url, "DELETE", **kwargs)

    def recreate_db(self, **kwargs):
        headers, body = self.post("/db")
        return body

    def create_deployment(self, auth_url, username, password, tenant_name):
        request = {"auth_url": auth_url,
                   "username": username,
                   "password": password,
                   "tenant_name": tenant_name}

        headers, body = self.post("/deployments", body=request)
        return body

    def list_deployments(self):
        headers, body = self.get("/deployments")
        return body

    def get_deployemnt(self, deployment_uuid):
        headers, body = self.get("/deployments/{0}".format(deployment_uuid))
        return body

    def recreate_deployment(self, deployment_uuid):
        headers, body = self.put("/deployments/{0}".format(deployment_uuid))
        return body

    def delete_deployment(self, deployment_uuid):
        headers, body = \
            self.delete("/deployments/{0}".format(deployment_uuid))
        return body

    def create_task(self, task_filename, task_params=None, tag=None,
                    deployment_uuid=None, abort_on_sla_failure=False):
        request = {
            "task_config": json.loads(file(task_filename).read()),
            "task_params": task_params if task_params is not None else {},
            "tag": tag,
            "deployment_uuid": deployment_uuid,
            "abort_on_sla_failure": abort_on_sla_failure}

        headers, body = self.post("/tasks", body=request)
        return body

    def list_tasks(self):
        headers, body = self.get("/tasks")
        return body

    def get_task(self, task_uuid):
        headers, body = self.get("/tasks/{0}".format(task_uuid))
        return body

    def get_task_log(self, task_uuid, start_line=-10, end_line=None):
        payload = {"start_line": start_line}
        if end_line is not None:
            payload.update({"end_line": end_line})
        headers, body = self.get("/tasks/{0}/log".format(task_uuid),
                                 params=payload)
        return body

    def get_task_result(self, task_uuid, download_dir="."):
        headers, body = self.get("/tasks/{0}/result".format(task_uuid),
                                 stream=True)
        path = os.path.join(download_dir,
                            "{0}-detailed-result.log".format(task_uuid))
        with open(path, "wb") as result:
            result.write(body)
        return "Downloaded: {0}".format(path)

    def get_task_report(self, task_uuid,
                        report_format='html',
                        download_dir="."):
        headers, body = self.get("/tasks/{0}/report".format(task_uuid),
                                 params={"format": report_format},
                                 stream=True)
        path = os.path.join(download_dir,
                            "{0}.{1}".format(task_uuid, report_format))
        with open(path, "wb") as result:
            result.write(body)
        return "Downloaded: {0}".format(path)

    def delete_task(self, task_uuid):
        headers, body = self.delete("/tasks/{0}".format(task_uuid))
        return body

    def install_tempest(self, deployment_uuid=None, tempest_source=None):
        request = {"tempest_source": tempest_source}
        headers, body = \
            self.post("/deployments/{0}/tempest".format(deployment_uuid),
                      body=request)
        return body

    def check_tempest(self, deployment_uuid):
        headers, body = \
            self.get("/deployments/{0}/tempest".format(deployment_uuid))
        return body

    def reinstall_tempest(self, deployment_uuid):
        headers, body = self.put(
            "/deployments/{0}/tempest".format(deployment_uuid))
        return body

    def uninstall_tempest(self, deployment_uuid):
        headers, body = self.delete(
            "/deployments/{0}/tempest".format(deployment_uuid))
        return body

    def run_verification(self, deployment_uuid, set_name=None,
                         regex=None, tempest_config=None):
        request = {
            "deployment_uuid": deployment_uuid,
            "set_name": set_name,
            "regex": regex,
            "tempest_config": tempest_config}
        headers, body = self.post("/verifications", body=request)
        return body

    def list_verifications(self):
        headers, body = self.get("/verifications")
        return body

    def get_verification(self, verification_uuid):
        headers, body = \
            self.get("/verifications/{0}".format(verification_uuid))
        return body

    def get_verification_result(self, verification_uuid, detailed=False):
        payload = {}
        if detailed:
            payload.update({"detailed": 1})

        headers, body = \
            self.get("/verifications/{0}/result".format(verification_uuid),
                     params=payload)
        return body

    def get_verification_report(self, verification_uuid, report_format='html',
                                download_dir="."):
        payload = {"report_format": report_format}
        headers, body = \
            self.get("/verifications/{0}/report".format(verification_uuid),
                     params=payload, stream=True)

        path = os.path.join(download_dir,
                            "tempest_{0}.{1}".format(verification_uuid,
                                                     report_format))
        with open(path, "wb") as result:
            result.write(body)
        return "Downloaded: {0}".format(path)
