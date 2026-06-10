import httpx
import pytest
from pytest_httpx import HTTPXMock


async def test_list_catalogs(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = {"data": [{"id": "docs", "title": "Gramax Docs"}]}
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.list_catalogs()

    assert result == response_data
    request = httpx_mock.get_request()
    assert "/api/catalogs" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-api-token-123"


async def test_get_navigation(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = {"data": [{"id": "getting-started", "title": "Начало работы"}]}
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.get_navigation("docs")

    assert result == response_data
    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/navigation" in str(request.url)


async def test_get_article_html(httpx_mock: HTTPXMock, base_url, api_token):
    html_content = "<h1>Заголовок</h1><p>Текст статьи.</p>"
    httpx_mock.add_response(text=html_content)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.get_article_html("docs", "getting-started")

    assert result == html_content
    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/articles/getting-started/html" in str(request.url)


async def test_get_article_html_encodes_article_id(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="<p>ok</p>")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        await client.get_article_html("docs", "deploy/docker")

    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/articles/deploy%2Fdocker/html" in str(request.url)


async def test_search(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = [{"type": "article", "title": [{"type": "text", "text": "Токен"}]}]
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.search("токен", catalog_name="docs")

    assert result == response_data
    request = httpx_mock.get_request()
    url_str = str(request.url)
    assert "/api/search/searchCommand" in url_str
    assert "catalogName=docs" in url_str


async def test_search_all_catalogs(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(json=[])

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.search("query")

    assert result == []
    request = httpx_mock.get_request()
    assert "catalogName" not in str(request.url)


async def test_search_with_filters(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(json=[])

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        await client.search(
            "naumen",
            catalog_name="docs",
            search_type="vector",
            language="ru",
            resource_filter="without",
            property_filter={"op": "eq", "key": "Продукт", "value": "NSD"},
        )

    request = httpx_mock.get_request()
    url_str = str(request.url)
    assert "type=vector" in url_str
    assert "articlesLanguage=ru" in url_str
    import json
    body = json.loads(request.content)
    assert body["resourceFilter"] == "without"
    assert body["propertyFilter"]["op"] == "eq"


async def test_search_no_body_without_filters(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(json=[])

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        await client.search("query")

    request = httpx_mock.get_request()
    assert request.content == b""


async def test_error_401(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=401, text="Unauthorized")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            await client.list_catalogs()


async def test_error_403(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=403, text="Forbidden")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            await client.list_catalogs()


async def test_error_404(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=404, text="Not Found")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNotFoundError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNotFoundError, match="не найден"):
            await client.get_navigation("bad-catalog")


async def test_ai_search_yields_text_chunks(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"hello"}\n'
        '{"type":"text","text":" world"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("test")]

    assert chunks == ["hello", " world"]
    request = httpx_mock.get_request()
    url_str = str(request.url)
    assert "/api/search/chat" in url_str
    assert "query=test" in url_str
    assert request.headers["authorization"] == "Bearer test-api-token-123"


async def test_ai_search_passes_all_params(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        async for _ in client.ai_search(
            "Что такое ITSM",
            catalog_name="commercial-knowlage",
            articles_language="ru",
            response_language="en",
            current_article="commercial-knowlage/intro",
        ):
            pass

    url_str = str(httpx_mock.get_request().url)
    assert "catalogName=commercial-knowlage" in url_str
    assert "articlesLanguage=ru" in url_str
    assert "responseLanguage=en" in url_str
    # currentArticle URL-encoded
    assert "currentArticle=commercial-knowlage" in url_str


async def test_ai_search_skips_invalid_json_lines(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"a"}\n'
        'this is not json\n'
        '\n'
        '{"type":"text","text":"b"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == ["a", "b"]


async def test_ai_search_skips_non_text_chunks(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"a"}\n'
        '{"type":"meta","data":{}}\n'
        '{"type":"text","text":"b"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == ["a", "b"]


async def test_ai_search_empty_stream(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == []


async def test_ai_search_401_raises_auth_error(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=401, text="Unauthorized")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            async for _ in client.ai_search("q"):
                pass


async def test_ai_search_404_raises_not_found(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=404, text="Not Found")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNotFoundError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNotFoundError, match="не найден"):
            async for _ in client.ai_search("q", catalog_name="missing"):
                pass


async def test_list_catalogs_anonymous(httpx_mock: HTTPXMock, base_url):
    """AC-4: GramaxClient with api_token=None sends no Authorization header."""
    httpx_mock.add_response(json={"data": []})

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=None) as client:
        await client.list_catalogs()

    request = httpx_mock.get_request()
    assert "authorization" not in request.headers


async def test_empty_string_token_no_header(httpx_mock: HTTPXMock, base_url):
    """AC-5: GramaxClient with api_token='' sends no Authorization header (defensive)."""
    httpx_mock.add_response(json={"data": []})

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token="") as client:
        await client.list_catalogs()

    request = httpx_mock.get_request()
    assert "authorization" not in request.headers


# get_navigation при ConnectError → GramaxNetworkError
async def test_get_navigation_connect_error_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            await client.get_navigation("docs")

    msg = str(exc_info.value)
    assert "docs" in msg
    assert "ConnectError" in msg


# get_navigation при невалидном JSON → GramaxNetworkError
async def test_get_navigation_invalid_json_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_response(status_code=200, text="<html>error</html>")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError):
            await client.get_navigation("docs")


# search при ConnectError → GramaxNetworkError
async def test_search_connect_error_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            await client.search("query")

    msg = str(exc_info.value)
    assert "ConnectError" in msg


# ai_search при ConnectError (до stream) → GramaxNetworkError
async def test_ai_search_connect_error_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            async for _ in client.ai_search("query"):
                pass

    msg = str(exc_info.value)
    assert "ConnectError" in msg


# AC-11: GramaxServerError и GramaxNetworkError — подклассы GramaxError
def test_gramax_server_error_is_subclass_of_gramax_error():
    from gramax_docportal_mcp.client import GramaxError, GramaxServerError

    assert issubclass(GramaxServerError, GramaxError)
    err = GramaxServerError("test")
    assert isinstance(err, GramaxError)


def test_gramax_network_error_is_subclass_of_gramax_error():
    from gramax_docportal_mcp.client import GramaxError, GramaxNetworkError

    assert issubclass(GramaxNetworkError, GramaxError)
    err = GramaxNetworkError("test")
    assert isinstance(err, GramaxError)


# AC-6: ai_search при HTTP 500 до начала стрима → GramaxServerError
async def test_ai_search_500_raises_server_error(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=500, text="Internal Server Error")

    from gramax_docportal_mcp.client import GramaxClient, GramaxServerError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxServerError) as exc_info:
            async for _ in client.ai_search("query"):
                pass

    msg = str(exc_info.value)
    assert "500" in msg


# AC-5: search при невалидном JSON в теле ответа → GramaxNetworkError
async def test_search_invalid_json_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_response(status_code=200, text="<html>not json</html>")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            await client.search("query")

    msg = str(exc_info.value)
    assert "нечитаемый" in msg or "JSON" in msg.upper() or "Gramax" in msg


# AC-4: get_article_html при TimeoutException → GramaxNetworkError с русским текстом
async def test_get_article_html_timeout_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_exception(httpx.ReadTimeout("Request timed out"))

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            await client.get_article_html("docs", "intro")

    msg = str(exc_info.value)
    assert "ожидания" in msg
    assert "intro" in msg or "docs" in msg


# AC-3: list_catalogs при ConnectError → GramaxNetworkError с русским текстом
async def test_list_catalogs_connect_error_raises_network_error(
    httpx_mock: HTTPXMock, base_url, api_token
):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    from gramax_docportal_mcp.client import GramaxClient, GramaxNetworkError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNetworkError) as exc_info:
            await client.list_catalogs()

    msg = str(exc_info.value)
    assert "подключиться" in msg or "Gramax" in msg
    assert "ConnectError" in msg


# AC-1: search при HTTP 500 → GramaxServerError с русским текстом содержащим "500"
async def test_search_500_raises_server_error(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=500, text="Internal Server Error")

    from gramax_docportal_mcp.client import GramaxClient, GramaxServerError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxServerError) as exc_info:
            await client.search("query", search_type="vector")

    msg = str(exc_info.value)
    assert "500" in msg
    assert "поиск" in msg.lower() or "query" in msg


# AC-2: search при HTTP 503 → GramaxServerError с русским текстом содержащим "503"
async def test_search_503_raises_server_error(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=503, text="Service Unavailable")

    from gramax_docportal_mcp.client import GramaxClient, GramaxServerError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxServerError) as exc_info:
            await client.search("query")

    assert "503" in str(exc_info.value)
