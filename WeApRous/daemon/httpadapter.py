#
# Copyright (C) 2025 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# WeApRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#

"""
daemon.httpadapter
~~~~~~~~~~~~~~~~~

This module provides a http adapter object to manage and persist 
http settings (headers, bodies). The adapter supports both
raw URL paths and RESTful route definitions, and integrates with
Request and Response objects to handle client-server communication.
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

class HttpAdapter:
    """
    A mutable :class:`HTTP adapter <HTTP adapter>` for managing client connections
    and routing requests.

    The `HttpAdapter` class encapsulates the logic for receiving HTTP requests,
    dispatching them to appropriate route handlers, and constructing responses.
    It supports RESTful routing via hooks and integrates with :class:`Request <Request>` 
    and :class:`Response <Response>` objects for full request lifecycle management.

    Attributes:
        ip (str): IP address of the client.
        port (int): Port number of the client.
        conn (socket): Active socket connection.
        connaddr (tuple): Address of the connected client.
        routes (dict): Mapping of route paths to handler functions.
        request (Request): Request object for parsing incoming data.
        response (Response): Response object for building and sending replies.
    """

    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        """
        Initialize a new HttpAdapter instance.

        :param ip (str): IP address of the client.
        :param port (int): Port number of the client.
        :param conn (socket): Active socket connection.
        :param connaddr (tuple): Address of the connected client.
        :param routes (dict): Mapping of route paths to handler functions.
        """

        #: IP address.
        self.ip = ip
        #: Port.
        self.port = port
        #: Connection
        self.conn = conn
        #: Conndection address
        self.connaddr = connaddr
        #: Routes
        self.routes = routes
        #: Request
        self.request = Request()
        #: Response
        self.response = Response()

    def handle_login(self, req, resp, body):
        """
        Handles the POST /login logic for Task 1A.
        - Parses the body
        - If admin/password, returns 200 OK, index.html, and Set-Cookie
        - Otherwise, returns 401 Unauthorized
        """
        creds = {}
        # Parse simple form body (from the raw body text)
        for pair in body.split("&"):
            if "=" in pair:
                try:
                    k, v = pair.split("=", 1)
                    creds[k] = v
                except ValueError:
                    pass # ignore malformed pairs

        print(f"[HttpAdapter] Login attempt with creds: {creds}")

        # Check credentials
        if creds.get("username") == "admin" and creds.get("password") == "password":
            print("[HttpAdapter] Login SUCCESSFUL")
            
            # Get the index.html content
            try:
                # Assumes the server is run from the `http_daemon` root directory
                with open('www/index.html', 'rb') as f:
                    html_content = f.read()
            except Exception as e:
                print(f"[HttpAdapter] ERROR: Could not read www/index.html: {e}")
                html_content = b"<html><body>Login OK but no index.html found.</body></html>"

            # Build the HTTP 200 OK response
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(html_content)}\r\n"
                "Set-Cookie: auth=true; Path=/\r\n"  # <-- The cookie for Task 1A
                "Connection: close\r\n"
                "\r\n"
            ).encode('utf-8') + html_content

            return response
        
        else:
            print("[HttpAdapter] Login FAILED")
            # Respond with 401 Unauthorized (Task 1A)
            response = (
                "HTTP/1.1 401 Unauthorized\r\n"
                "Content-Type: text/html\r\n"
                "Content-Length: 22\r\n"
                "Connection: close\r\n"
                "\r\n"
                "<h1>401 Unauthorized</h1>"
            ).encode('utf-8')
            return response

    def handle_client(self, conn, addr, routes):
        """
        Handle an incoming client connection.
        """

        # Connection handler.
        self.conn = conn        
        # Connection address.
        self.connaddr = addr
        # Request handler
        req = self.request
        # Response handler
        resp = self.response

        try:
            # Handle the request
            msg = conn.recv(1024).decode()

            body = ""
            if "\r\n\r\n" in msg:
                parts = msg.split("\r\n\r\n", 1)
                if len(parts) > 1:
                    body = parts[1]
                    
            req.prepare(msg, routes)

            # ---  TASK 1A (Login Bypass) ---
            # Check for POST /login *before* the cookie guard
            if req.method == "POST" and req.path == "/login.html":
                print("[HttpAdapter] TASK 1A: Handling /login bypass")
                # Call our new login handler
                login_response = self.handle_login(req, resp, body)
                conn.sendall(login_response)
                conn.close()
                return # Login handled, we are done.

            # --- TASK 1B: COOKIE-BASED ACCESS CONTROL ---
            # This code is now only reached if the request is NOT POST /login.
            
            protected_path = '/index.html' 
            if req.path == '/':
                req.path = '/index.html'
                
            if req.path == protected_path:
                # req.cookies is populated by req.prepare()
                if req.cookies.get('auth') != 'true':
                    print("[HttpAdapter] TASK 1B: UNAUTHORIZED access to {}. Missing or invalid cookie.".format(req.path))
                    
                    # Send 401 Unauthorized page (as per Task 1B)
                    response = (
                        "HTTP/1.1 401 Unauthorized\r\n"
                        "Content-Type: text/html\r\n"
                        "Content-Length: 22\r\n"
                        "Connection: close\r\n"
                        "\r\n"
                        "<h1>401 Unauthorized</h1>"
                    ).encode('utf-8')
                    
                    conn.sendall(response)
                    conn.close()
                    return

            # --- Handle other hooks (if any) or static files ---
            
            # Check for other hooks (that were not /login)
            if req.hook: 
                print("[HttpAdapter] Handling other hook for: {}".format(req.path))
                hook_result = req.hook(headers=req.headers, body=body)
                if hook_result is not None:
                    if isinstance(hook_result, bytes):
                        conn.sendall(hook_result)
                    elif isinstance(hook_result, str):
                        conn.sendall(hook_result.encode('utf-8'))
                    conn.close()
                    return

            # Build response for static files
            # (This will now correctly serve /index.html if cookie was valid)
            response = resp.build_response(req)

            #print(response)
            conn.sendall(response)
            
        except Exception as e:
            print(f"[HttpAdapter] Error in handle_client: {e}")
            # Send a 500
            try:
                error_response = (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: text/html\r\n"
                    "Content-Length: 22\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    "<h1>500 Server Error</h1>"
                ).encode('utf-8')
                conn.sendall(error_response)
            except:
                pass # Connection may be dead
        finally:
            try:
                conn.close()
            except:
                pass

    @property
    def extract_cookies(self, req, resp):
        """
        Build cookies from the :class:`Request <Request>` headers.

        :param req:(Request) The :class:`Request <Request>` object.
        :param resp: (Response) The res:class:`Response <Response>` object.
        :rtype: cookies - A dictionary of cookie key-value pairs.
        """
        cookies = {}
        # Get the raw cookie string from the headers dict
        cookie_str = req.headers.get("cookie", "") 
        if cookie_str:
            for pair in cookie_str.split(";"):
                try:
                    # Split only on the first '='
                    key, value = pair.strip().split("=", 1) 
                    cookies[key] = value
                except ValueError:
                    pass # Ignore malformed cookie pairs
        return cookies

    def build_response(self, req, resp):
        """Builds a :class:`Response <Response>` object 

        :param req: The :class:`Request <Request>` used to generate the response.
        :param resp: The  response object.
        :rtype: Response
        """
        response = Response()

        # Set encoding.
        # response.encoding = get_encoding_from_headers(response.headers)
        response.raw = resp
        # response.reason = response.raw.reason

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        # Add new cookies from the server.
        response.cookies = self.extract_cookies(req,resp)

        # Give the Response some context.
        response.request = req
        response.connection = self

        return response

    # def get_connection(self, url, proxies=None):
        # """Returns a url connection for the given URL. 

        # :param url: The URL to connect to.
        # :param proxies: (optional) A Requests-style dictionary of proxies used on this request.
        # :rtype: int
        # """

        # proxy = select_proxy(url, proxies)

        # if proxy:
            # proxy = prepend_scheme_if_needed(proxy, "http")
            # proxy_url = parse_url(proxy)
            # if not proxy_url.host:
                # raise InvalidProxyURL(
                    # "Please check proxy URL. It is malformed "
                    # "and could be missing the host."
                # )
            # proxy_manager = self.proxy_manager_for(proxy)
            # conn = proxy_manager.connection_from_url(url)
        # else:
            # # Only scheme should be lower case
            # parsed = urlparse(url)
            # url = parsed.geturl()
            # conn = self.poolmanager.connection_from_url(url)

        # return conn


    def add_headers(self, request):
        """
        Add headers to the request.

        This method is intended to be overridden by subclasses to inject
        custom headers. It does nothing by default.

        
        :param request: :class:`Request <Request>` to add headers to.
        """
        pass

    def build_proxy_headers(self, proxy):
        """Returns a dictionary of the headers to add to any request sent
        through a proxy. 

        :class:`HttpAdapter <HttpAdapter>`.

        :param proxy: The url of the proxy being used for this request.
        :rtype: dict
        """
        headers = {}
        #
        # TODO: build your authentication here
        #       username, password =...
        # we provide dummy auth here
        #
        username, password = ("user1", "password")

        if username:
            headers["Proxy-Authorization"] = (username, password)

        return headers