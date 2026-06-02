import asyncio
import logging
import uuid
import time
import os
from urllib.parse import quote_plus
from typing import Optional

logger = logging.getLogger("Brain.VisualBrowser")

class VisualBrowserService:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()
        self._last_screenshot: bytes = b""
        self._is_active = False

    async def start(self):
        async with self._lock:
            if self._page:
                return
            logger.info("Initializing Playwright Chromium browser...")
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1024, "height": 768}
                )
                self._page = await self._context.new_page()
                self._is_active = True
                logger.info("Playwright Chromium browser started successfully.")
            except Exception as e:
                logger.error(f"Failed to start Playwright browser: {e}")
                self._playwright = None
                self._browser = None
                self._context = None
                self._page = None
                self._is_active = False
                raise RuntimeError(f"Playwright initialization failed: {e}")

    async def stop(self):
        async with self._lock:
            self._is_active = False
            if self._page:
                try:
                    await self._page.close()
                except Exception:
                    pass
                self._page = None
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            logger.info("Playwright Chromium browser stopped.")

    async def get_page(self):
        if not self._page:
            await self.start()
        return self._page

    async def open(self, url: str):
        page = await self.get_page()
        logger.info(f"Opening URL: {url}")
        await self._publish_event(
            phase="reading",
            title="فتح الموقع",
            detail=url
        )
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1.0)
        await self.update_screenshot()

    async def _is_captcha(self, page) -> bool:
        try:
            content = (await page.content()).lower()
            title = (await page.title()).lower()
            return (
                "not a robot" in content or 
                "captcha" in content or 
                "recaptcha" in content or
                "unusual traffic" in content or
                "our systems have detected" in content or
                "security check" in title or
                "captcha" in title
            )
        except Exception:
            return False

    async def search(self, query: str) -> str:
        page = await self.get_page()
        logger.info(f"Searching web for: {query}")
        await self._publish_event(
            phase="searching",
            title="جاري البحث في الويب",
            detail=query
        )
        url = f"https://www.google.com/search?q={quote_plus(query)}&hl=ar"
        links = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
            await self.update_screenshot()
            
            if await self._is_captcha(page):
                logger.warning("Google CAPTCHA detected. Falling back to DuckDuckGo...")
            else:
                # Get links
                links = await page.eval_on_selector_all(
                    "div.g a",
                    "els => els.map(el => el.href).filter(href => href && href.startsWith('http'))"
                )
        except Exception as e:
            logger.warning(f"Google search navigation failed: {e}. Falling back to DuckDuckGo...")

        # Clean Google links to avoid search engine or helper links
        links = [
            link for link in links 
            if not any(domain in link.lower() for domain in ["google.com", "google.com.eg", "gstatic.com", "youtube.com", "play.google.com"])
        ]

        if not links:
            logger.info("Falling back to DuckDuckGo search...")
            await self._publish_event(
                phase="searching",
                title="البحث البديل (DuckDuckGo)",
                detail="جاري استخدام DuckDuckGo لتفادي الحظر..."
            )
            url = f"https://duckduckgo.com/?q={quote_plus(query)}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.0)
                await self.update_screenshot()
                raw_links = await page.eval_on_selector_all(
                    "a",
                    "els => els.map(el => el.href).filter(href => href && href.startsWith('http'))"
                )
                links = [
                    link for link in raw_links 
                    if not any(domain in link.lower() for domain in ["duckduckgo.com", "google.com", "bing.com", "yahoo.com", "wikipedia.org/wiki/special:", "wikipedia.org/wiki/file:"])
                ]
            except Exception as e:
                logger.error(f"DuckDuckGo search failed: {e}")
                links = []

        extracted_texts = []
        if links:
            target_link = links[0]
            logger.info(f"Visual browser visiting top search result: {target_link}")
            await self._publish_event(
                phase="reading",
                title="قراءة نتيجة البحث الأولى",
                detail=target_link
            )
            try:
                await page.goto(target_link, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.0)
                await self.update_screenshot()
                
                # Scroll down to read
                await self.scroll("down", 400)
                await self.scroll("down", 400)
                
                # Extract text
                page_text = await page.evaluate("() => document.body.innerText")
                page_text_clean = " ".join(page_text.split())
                extracted_texts.append(f"Source: {target_link}\nContent: {page_text_clean[:1500]}")
            except Exception as e:
                logger.error(f"Failed to visit search result link: {e}")
                # Fallback to search results page itself
                search_text = await page.evaluate("() => document.body.innerText")
                extracted_texts.append(f"Source: Search Results\nContent: {search_text[:1000]}")
        else:
            search_text = await page.evaluate("() => document.body.innerText")
            extracted_texts.append(f"Source: Search Results\nContent: {search_text[:1000]}")

        await self._publish_event(
            phase="analyzing",
            title="تم الانتهاء من البحث المرئي",
            detail="جاري تحليل البيانات المستخرجة..."
        )
        return "\n\n".join(extracted_texts)

    async def scroll(self, direction: str = "down", amount: int = 500):
        page = await self.get_page()
        logger.info(f"Scrolling page {direction} by {amount}px")
        await self._publish_event(
            phase="reading",
            title="تصفح الصفحة",
            detail=f"سكرول {direction} بمقدار {amount}px"
        )
        scroll_y = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {scroll_y})")
        await asyncio.sleep(0.5)
        await self.update_screenshot()

    async def screenshot_jpeg(self) -> bytes:
        if not self._last_screenshot:
            # Return a simple 1x1 black pixel JPEG as placeholder if no screenshot yet
            return b'\xff\xd8\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
        return self._last_screenshot

    async def update_screenshot(self):
        if self._page:
            try:
                self._last_screenshot = await self._page.screenshot(type="jpeg", quality=60)
            except Exception as e:
                logger.error(f"Failed to capture visual browser screenshot: {e}")

    async def _publish_event(self, phase: str, title: str, detail: str = ""):
        try:
            from brain.activity.bus import get_activity_bus
            from brain.activity.types import ChestActivityEvent
            
            event = ChestActivityEvent(
                id=str(uuid.uuid4()),
                tsMs=int(time.time() * 1000),
                phase=phase,
                source="browser",
                title=title,
                detail=detail,
                emotion="searching" if phase == "searching" else "thinking",
                artifacts={"browserLive": True}
            )
            bus = get_activity_bus()
            await bus.publish(event)
        except Exception as e:
            logger.error(f"Error publishing visual browser activity event: {e}")

# Global lazy singleton instance
_visual_browser = None

def get_visual_browser() -> VisualBrowserService:
    global _visual_browser
    if _visual_browser is None:
        _visual_browser = VisualBrowserService()
    return _visual_browser
