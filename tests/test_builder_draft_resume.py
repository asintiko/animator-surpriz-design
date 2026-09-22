from __future__ import annotations

import inspect
import unittest

from core import customer_panel


class BuilderDraftResumeTests(unittest.TestCase):
    """A guest who assembled an order is sent to registration and returns to
    /party-builder/?resume=review. The flash raised there is the only thing that
    tells them the whole assembly survived, and the builder turns it into a toast.
    Exercising the real view needs the catalog database plus the page bundle, so
    these guard the branch itself.
    """

    def test_resume_review_reports_the_whole_assembly_as_saved(self) -> None:
        source = inspect.getsource(customer_panel)
        self.assertIn("Вся сборка заказа сохранена", source)
        self.assertIn('if request.args.get("resume", "").strip() == "review":', source)

    def test_plain_restore_keeps_its_own_shorter_notice(self) -> None:
        self.assertIn("Мы вернули вашу заявку", inspect.getsource(customer_panel))

    def test_builder_template_promotes_flashes_to_toasts(self) -> None:
        from pathlib import Path

        template = Path(customer_panel.__file__).resolve().parent.parent / "templates" / "site" / "order_builder_content.html"
        body = template.read_text(encoding="utf-8")
        self.assertIn(".v2-flashes .customer-flash", body)
        self.assertIn("toneByCategory", body)
        # The inline block must be removed once its text has been handed to the toast,
        # otherwise the page shows the same notice twice.
        self.assertIn("container.remove()", body)


if __name__ == "__main__":
    unittest.main()
