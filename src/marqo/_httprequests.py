import copy
import json
import pprint
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, Union
import requests
from marqo.config import Config
from marqo.errors import (
    MarqoWebError,
    MarqoCommunicationError,
    MarqoTimeoutError,
    IndexNotFoundError
)
from marqo.version import qualified_version

ALLOWED_OPERATIONS = {requests.delete, requests.get, requests.post, requests.put}

OPERATION_MAPPING = {'delete': requests.delete, 'get': requests.get,
                     'post': requests.post, 'put': requests.put}


class HttpRequests:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.headers = dict()

    def send_request(
        self,
        http_method: Callable,
        path: str,
        body: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[str], str]] = None,
        content_type: Optional[str] = None,
    ) -> Any:
        to_verify = False #  self.config.cluster_is_remote

        if http_method not in ALLOWED_OPERATIONS:
            raise ValueError("{} not an allowed operation {}".format(http_method, ALLOWED_OPERATIONS))

        req_headers = copy.deepcopy(self.headers)

        if content_type is not None and content_type:
            req_headers['Content-Type'] = content_type

        try:
            request_path = self.config.url + '/' + path
            if isinstance(body, bytes):
                response = http_method(
                    request_path,
                    timeout=self.config.timeout,
                    headers=req_headers,
                    data=body,
                    verify=to_verify
                )
            elif isinstance(body, str):
                response = http_method(
                    request_path,
                    timeout=self.config.timeout,
                    headers=req_headers,
                    data=body,
                    verify=to_verify
                )
            else:
                response = http_method(
                    request_path,
                    timeout=self.config.timeout,
                    headers=req_headers,
                    data=json.dumps(body) if body else None,
                    verify=to_verify
                )
            return self.__validate(response)

        except requests.exceptions.Timeout as err:
            raise MarqoTimeoutError(str(err)) from err
        except requests.exceptions.ConnectionError as err:
            raise MarqoCommunicationError(str(err)) from err

    def get(
        self, path: str,
        body: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[str], str]] = None,
    ) -> Any:
        content_type = None
        if body is not None:
            content_type = 'application/json'
        return self.send_request(requests.get, path=path, body=body, content_type=content_type)

    def post(
        self,
        path: str,
        body: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[str], str]] = None,
        content_type: Optional[str] = 'application/json',
    ) -> Any:
        return self.send_request(requests.post, path, body, content_type)

    def put(
        self,
        path: str,
        body: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[str], str]] = None,
        content_type: Optional[str] = None,
    ) -> Any:
        if body is not None:
            content_type = 'application/json'
        return self.send_request(requests.put, path, body, content_type)

    def delete(
        self,
        path: str,
        body: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[str]]] = None,
    ) -> Any:
        return self.send_request(requests.delete, path, body)

    @staticmethod
    def __to_json(
        request: requests.Response
    ) -> Any:
        if request.content == b'':
            return request
        return request.json()

    @staticmethod
    def __validate(
        request: requests.Response
    ) -> Any:
        try:
            request.raise_for_status()
            return HttpRequests.__to_json(request)
        except requests.exceptions.HTTPError as err:
            convert_to_marqo_web_error_and_raise(response=request, err=err)


def convert_to_marqo_web_error_and_raise(response: requests.Response, err: requests.exceptions.HTTPError):
    """Translates OpenSearch errors into Marqo errors"""
    print("\nresponse, status code:")
    print(response.status_code)
    print("response, JSON body:")
    pprint.pprint(response.json())
    try:
        response_dict = response.json()
        open_search_error_type = response_dict["error"]["type"]

        if open_search_error_type == "index_not_found_exception":
            raise IndexNotFoundError(
                message=f"Index `{response_dict['error']['index']}` not found."
            ) from err

    except KeyError:
        # An error was encountered trying to read the error JSON - just pass the error message through
        raise MarqoWebError(message=response.text, code="unhandled_backend_error", status_code=HTTPStatus(
            response.status_code, '')) from err

