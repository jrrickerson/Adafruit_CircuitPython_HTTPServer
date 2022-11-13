try:
    from typing import Optional, Dict, Union
    from socket import socket
except ImportError:
    pass

from errno import EAGAIN, ECONNRESET
import os

from socketpool import SocketPool

from .mime_type import MIMEType
from .status import HTTPStatus, OK_200, NOT_FOUND_404

class HTTPResponse:
    """Details of an HTTP response. Use in `HTTPServer.route` decorator functions."""

    http_version: str
    status: HTTPStatus
    headers: Dict[str, str]
    content_type: str

    filename: Optional[str]
    root_path: str

    body: str

    def __init__(
        self,
        status: HTTPStatus = OK_200,
        body: str = "",
        headers: Dict[str, str] = None,
        content_type: str = MIMEType.TEXT_PLAIN,
        filename: Optional[str] = None,
        root_path: str = "",
        http_version: str = "HTTP/1.1"
    ) -> None:
        """
        Creates an HTTP response.

        Returns `body` if `filename` is `None`, otherwise returns the contents of `filename`.
        """

        self.status = status
        self.body = body
        self.headers = headers or {}
        self.content_type = content_type
        self.filename = filename
        self.root_path = root_path
        self.http_version = http_version

    @staticmethod
    def _construct_response_bytes(
        http_version: str = "HTTP/1.1",
        status: HTTPStatus = OK_200,
        content_type: str = "text/plain",
        content_length: Union[int, None] = None,
        headers: Dict[str, str] = None,
        body: str = "",
    ) -> str:
        """Send the constructed response over the given socket."""

        response = f"{http_version} {status.code} {status.text}\r\n"

        headers = headers or {}

        headers["Content-Type"] = content_type
        headers["Content-Length"] = content_length if content_length is not None else len(body)
        headers["Connection"] = "close"

        for header, value in headers.items():
            response += f"{header}: {value}\r\n"

        response += f"\r\n{body}"

        return response

    def send(self, conn: Union[SocketPool.Socket, socket.socket]) -> None:
        """
        Send the constructed response over the given socket.
        """

        if self.filename is not None:
            try:
                file_length = os.stat(self.root_path + self.filename)[6]
                self._send_file_response(
                    conn,
                    filename = self.filename,
                    root_path = self.root_path,
                    file_length = file_length
                )
            except OSError:
                self._send_response(
                    conn,
                    status = NOT_FOUND_404,
                    content_type = MIMEType.TEXT_PLAIN,
                    body = f"{NOT_FOUND_404} {self.filename}",
                )
        else:
            self._send_response(
                conn,
                status = self.status,
                content_type = self.content_type,
                headers = self.headers,
                body = self.body,
            )

    def _send_response(
        self,
        conn: Union[SocketPool.Socket, socket.socket],
        status: HTTPStatus,
        content_type: str,
        body: str,
        headers: Dict[str, str] = None
    ):
        self._send_bytes(
            conn,
            self._construct_response_bytes(
                status = status,
                content_type = content_type,
                headers = headers,
                body = body,
            )
        )

    def _send_file_response(
        self,
        conn: Union[SocketPool.Socket, socket.socket],
        filename: str,
        root_path: str,
        file_length: int
    ):
        self._send_bytes(
            conn,
            self._construct_response_bytes(
                status = self.status,
                content_type = MIMEType.mime_type(filename),
                content_length = file_length
            ),
        )
        with open(root_path + filename, "rb") as file:
            while bytes_read := file.read(2048):
                self._send_bytes(conn, bytes_read)

    @staticmethod
    def _send_bytes(
        conn: Union[SocketPool.Socket, socket.socket],
        buffer: Union[bytes, bytearray, memoryview],
    ):
        bytes_sent = 0
        bytes_to_send = len(buffer)
        view = memoryview(buffer)
        while bytes_sent < bytes_to_send:
            try:
                bytes_sent += conn.send(view[bytes_sent:])
            except OSError as exc:
                if exc.errno == EAGAIN: continue
                if exc.errno == ECONNRESET: return
