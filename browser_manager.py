import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def read_only_route(route):
    if route.request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        route.abort()
    else:
        route.continue_()


class BrowserManager:
    def __init__(self, profile, url):
        self.profile = Path(profile)
        self.url = url

    def __enter__(self):
        self.runtime = sync_playwright().start()
        try:
            self.context = self.runtime.chromium.launch_persistent_context(
                str(self.profile), headless=False, accept_downloads=False,
                service_workers='block',
                executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
            # Chromium alone cannot prevent actions made manually by the user.
            # Automation allows page navigation and blocks non-read HTTP methods.
            # Login may require POST. Enable protection after manual login.
            self.guard = read_only_route
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto(self.url, wait_until='domcontentloaded')
            return self
        except BaseException:
            if hasattr(self, 'context'):
                self.context.close()
            self.runtime.stop()
            raise

    def protect_read_phase(self):
        self.context.route('**/*', self.guard)

    def __exit__(self, *args):
        self.context.close()
        self.runtime.stop()
