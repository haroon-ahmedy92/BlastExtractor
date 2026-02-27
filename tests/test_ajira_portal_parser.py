from app.sites.ajira_portal import parse_listing_stubs_from_html


def test_parse_listing_stubs_from_table_html() -> None:
    sample_html = """
    <html>
      <body>
        <table>
          <tbody>
            <tr>
              <td>Systems Analyst</td>
              <td>Ministry of Tech</td>
              <td>3 Posts</td>
              <td>Deadline: 15/03/2026</td>
              <td><a href="/vacancies/123/details">Details</a></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    items = parse_listing_stubs_from_html(sample_html, base_url="https://portal.ajira.go.tz/vacancies")

    assert len(items) == 1
    assert items[0].title == "Systems Analyst"
    assert items[0].institution == "Ministry of Tech"
    assert items[0].number_of_posts == 3
    assert str(items[0].deadline_date) == "2026-03-15"
    assert str(items[0].details_url) == "https://portal.ajira.go.tz/vacancies/123/details"


def test_parse_table_row_without_link_uses_fallback_url() -> None:
    sample_html = """
    <html>
      <body>
        <table>
          <tbody>
            <tr>
              <td>1</td>
              <td>
                <div>PROCUREMENT OFFICER II</div>
                <div>Number of Posts: 2</div>
              </td>
              <td>Bodi ya Nafaka</td>
              <td>10/03/2026</td>
              <td><button type="button">Login to Apply</button></td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    items = parse_listing_stubs_from_html(sample_html, base_url="https://portal.ajira.go.tz/vacancies")

    assert len(items) == 1
    assert items[0].title == "PROCUREMENT OFFICER II"
    assert items[0].number_of_posts == 2
    assert str(items[0].deadline_date) == "2026-03-10"
    assert str(items[0].details_url) == "https://portal.ajira.go.tz/vacancies?row=1"


def test_parse_listing_stubs_from_card_html() -> None:
    sample_html = """
    <html>
      <body>
        <section>
          <article class="vacancy-card">
            <h3>Data Engineer</h3>
            <p>Institution: Public Data Agency</p>
            <p>Number of posts: 2</p>
            <p>Closing Date - 2026-04-01</p>
            <a href="https://portal.ajira.go.tz/job/8891">View Details</a>
          </article>
        </section>
      </body>
    </html>
    """
    items = parse_listing_stubs_from_html(sample_html)

    assert len(items) == 1
    assert items[0].title == "Data Engineer"
    assert items[0].institution == "Public Data Agency"
    assert items[0].number_of_posts == 2
    assert str(items[0].deadline_date) == "2026-04-01"
    assert str(items[0].details_url) == "https://portal.ajira.go.tz/job/8891"


def test_link_parser_ignores_nav_and_store_links() -> None:
    sample_html = """
    <html>
      <body>
        <a href="/vacancies">VACANCIES</a>
        <a href="https://play.google.com/store/apps/details?id=tz.go.ajira.apps.ajiraApp">App</a>
        <article>
          <h3>Data Engineer</h3>
          <p>Institution: Public Data Agency</p>
          <p>Number of posts: 2</p>
          <p>Closing Date - 2026-04-01</p>
          <a href="https://portal.ajira.go.tz/view-advert/abc123">View Details</a>
        </article>
      </body>
    </html>
    """
    items = parse_listing_stubs_from_html(sample_html)

    assert len(items) == 1
    assert items[0].title == "Data Engineer"
    assert str(items[0].details_url) == "https://portal.ajira.go.tz/view-advert/abc123"
