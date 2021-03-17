# HCaptcha wrapper for python made by me.
import requests

# Local constants.
VERIFY_URL = "https://hcaptcha.com/siteverify"

class HCaptcha:
    """A syncronous wrapper around Cloudflare's HCaptcha API used for anti
    bot measures."""

    def __init__(self, site_key: str, secret_key: str) -> None:
        """Configures the HCaptcha to be used properly. /shrug.
        
        Args:
            site_key (str): Fetched from the hcaptcha dashboard, public key
                directly included in the HTML.
            secret_key (str): Private key used for authentication on the
                backend. Also fetched from the HCaptcha website.
        """

        self.site_key: str = site_key
        self._secret_key: str = secret_key
    
    def verify(self, hc_resp: str, ip: str = None) -> bool:
        """Contacts the HCaptcha API to validate a captcha pass.
        
        Note:
            This is a full on HTTP request so its on the slower side.
            
        Args:
            hc_resp (str): The `h-captcha-response` post argument sent by a
                form with HCaptcha in it.
            ip (str): Optional IP of the user trying to pass the captcha.
        
        Returns:
            `bool` corresponding to whether the captcha is passed or failed.
        """

        post_arg = {
            "secret": self._secret_key,
            "response": hc_resp,
            "sitekey": self.site_key
        }

        # If we have the IP of the user, send it too.
        if ip is not None: post_arg["remoteip"] = ip

        try:
            r = requests.post(VERIFY_URL, post_arg).json()
        
        # Prevent a connection issue killing the thing.
        except Exception: return False

        return r["success"]
    
    def html(self, script: bool = False) -> str:
        """Generates the HCaptcha html you can include inside your page.
        
        Args:
            script (bool): Whether the HCaptcha script tag should also be
                included in the return.
        
        Returns:
            HTML format string.
        """

        html = ""

        if script:
            html = """<script src="https://hcaptcha.com/1/api.js" async defer></script>"""
        
        html += f"""<div class="h-captcha" data-sitekey="{self.site_key}"></div>"""
        return html
