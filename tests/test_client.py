import pytest
from pytest_httpx import HTTPXMock


@pytest.fixture
def base_url():
    return "https://docs.example.com"


@pytest.fixture
def api_token():
    return "test-api-token-123"


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
