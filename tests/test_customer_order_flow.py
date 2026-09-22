from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from flask import Flask, Response, session

from core import customer_panel
from core.customer_store import CUSTOMER_SESSION_KEY


class CustomerOrderFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY="test-secret", TESTING=True)
        customer_panel.register_customer_routes(self.app)

    def test_safe_next_url_rejects_external_and_browser_ambiguous_targets(self) -> None:
        fallback = "/account/"
        unsafe_targets = (
            "https://evil.example/after-otp",
            "//evil.example/after-otp",
            r"/\evil.example/after-otp",
            "/account/\x00after-otp",
            "/account/\x85after-otp",
        )

        for target in unsafe_targets:
            with self.subTest(target=target):
                self.assertEqual(customer_panel._safe_next_url(target, fallback), fallback)

        self.assertEqual(
            customer_panel._safe_next_url("/party-builder/?resume=review", fallback),
            "/party-builder/?resume=review",
        )

    def test_builder_uses_responsive_media_only_when_every_variant_exists(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            landing_root = Path(temporary_directory)
            media_directory = landing_root / "assets/img/characters"
            media_directory.mkdir(parents=True)
            item = {"slug": "admin-created-hero", "hero_file_path": ""}

            self.assertEqual(
                customer_panel._builder_responsive_media_base(
                    item,
                    "character",
                    landing_root=landing_root,
                ),
                "",
            )

            for width in (480, 768, 1200):
                for extension in ("avif", "webp"):
                    (media_directory / f"admin-created-hero-{width}.{extension}").touch()

            self.assertEqual(
                customer_panel._builder_responsive_media_base(
                    item,
                    "character",
                    landing_root=landing_root,
                ),
                "/surpriz/assets/img/characters/admin-created-hero",
            )

    def test_builder_derives_curated_variant_base_from_live_media_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            landing_root = Path(temporary_directory)
            media_directory = landing_root / "assets/img/characters"
            media_directory.mkdir(parents=True)
            for width in (480, 768, 1200):
                for extension in ("avif", "webp"):
                    (media_directory / f"white-rabbit-{width}.{extension}").touch()

            self.assertEqual(
                customer_panel._builder_responsive_media_base(
                    {
                        "slug": "white-labubu",
                        "hero_file_path": "/surpriz/assets/img/characters/white-rabbit-800.webp",
                    },
                    "character",
                    landing_root=landing_root,
                ),
                "/surpriz/assets/img/characters/white-rabbit",
            )

    def test_builder_prefers_uploaded_generated_cover_over_curated_slug(self) -> None:
        generated_base = "/media/generated/v1-sharp035/ab/abcdef"
        item = {
            "slug": "spiderman",
            "hero_file_path": f"{generated_base}/1920.webp",
        }
        groups = [{"items": [item]}]

        customer_panel._decorate_builder_media([], groups)

        self.assertIn(f"{generated_base}/480.avif 480w", item["responsive_avif_srcset"])
        self.assertEqual(item["responsive_media_fallback"], f"{generated_base}/1920.webp")

    def test_desktop_payment_button_uses_the_validated_step_transition(self) -> None:
        template_path = Path(__file__).resolve().parents[1] / "templates/site/order_builder_content.html"
        template = template_path.read_text(encoding="utf-8")
        handler = template.split('if (event.target.closest("[data-payment-step-button]")) {', 1)[1].split(
            "}", 1
        )[0]

        self.assertIn("moveStep(1);", handler)
        self.assertNotIn("goToStep(6);", handler)

    def test_api_send_code_sanitizes_ambiguous_next_before_storing_challenge(self) -> None:
        sent = {
            "success": True,
            "request_id": "request-id",
            "phone_e164": "+998901234567",
            "phone_display": "+998 90 123 45 67",
            "ttl": 300,
            "cooldown": 60,
        }
        with patch.object(customer_panel, "_start_telegram_auth", return_value=sent) as start_auth:
            response = self.app.test_client().post(
                "/api/auth/send-telegram-code",
                json={
                    "phone": "+998901234567",
                    "purpose": "login",
                    "next": r"/\evil.example/after-otp",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_auth.call_args.kwargs["next_url"], "/account/")

    def test_verified_auth_rejects_unsafe_redirect_from_legacy_challenge(self) -> None:
        challenge = {
            "purpose": "login",
            "full_name": "",
            "next_url": r"/\evil.example/after-otp",
        }
        completed = {"success": True, "customer": {"id": 7, "full_name": "Тест"}}

        with self.app.test_request_context("/auth/telegram-code/"):
            with (
                patch.object(customer_panel, "_load_challenge", return_value=challenge),
                patch.object(customer_panel, "_check_gateway_code", return_value={"success": True, "verified": True}),
                patch.object(customer_panel, "complete_customer_phone_auth", return_value=completed),
                patch.object(customer_panel, "_update_challenge"),
            ):
                result = customer_panel._verify_telegram_auth("+998901234567", "request-id", "123456")

        self.assertTrue(result["success"])
        self.assertEqual(result["redirect_url"], "/account/")

    def test_builder_form_keeps_nested_gift_choice(self) -> None:
        form = {
            "program_slug": "ribbon-show",
            "character_slugs": ["anna-elsa-olaf"],
            "ensemble_members": ["anna-elsa-olaf::Анна", "anna-elsa-olaf::Олаф"],
            "gift_choice_default": "balloons",
            "contact_name": "Мадина",
            "contact_phone": "+998 (90) 123-45-67",
        }
        with self.app.test_request_context("/party-builder/", method="POST", data=form):
            collected = customer_panel._collect_builder_form()

        self.assertEqual(collected["program_slug"], "ribbon-show")
        self.assertEqual(collected["character_slugs"], ["anna-elsa-olaf"])
        self.assertEqual(
            collected["ensemble_members"],
            ["anna-elsa-olaf::Анна", "anna-elsa-olaf::Олаф"],
        )
        self.assertEqual(collected["gift_choices"], {"default": "balloons"})
        self.assertEqual(collected["contact_name"], "Мадина")
        self.assertEqual(collected["contact_phone"], "+998 (90) 123-45-67")

    def test_guest_order_needs_no_registration_and_is_remembered(self) -> None:
        """Заказ без входа: гость заводится как аккаунт с неподтверждённым телефоном,
        а его public_id запоминается в сессии — сессию покупателя не выдаём."""
        guest = {"success": True, "customer": {"id": 42}, "created": True}
        created = {"success": True, "order": {"public_id": "SRP-00007"}}

        with (
            patch.object(customer_panel, "list_show_programs_for_public", return_value=[]),
            patch.object(customer_panel, "list_show_programs_grouped_for_public", return_value=[]),
            patch.object(customer_panel, "ensure_guest_customer", return_value=guest) as ensure_guest,
            patch.object(customer_panel, "create_party_order", return_value=created) as create_order,
        ):
            client = self.app.test_client()
            response = client.post(
                "/party-builder/",
                data={
                    "program_slug": "ribbon-show",
                    "contact_name": "Мадина",
                    "contact_phone": "+998 (90) 123-45-67",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/register/", response.headers["Location"])
        self.assertIn("SRP-00007", response.headers["Location"])
        ensure_guest.assert_called_once_with("+998 (90) 123-45-67", "Мадина")
        self.assertEqual(create_order.call_args.args[0], 42)

        with client.session_transaction() as saved_session:
            self.assertEqual(saved_session[customer_panel.GUEST_ORDERS_SESSION_KEY], ["SRP-00007"])
            self.assertNotIn(CUSTOMER_SESSION_KEY, saved_session)

    def test_guest_order_without_contacts_does_not_reach_the_database(self) -> None:
        refusal = {"success": False, "message": "Укажите номер телефона."}

        with (
            patch.object(customer_panel, "list_show_programs_for_public", return_value=[]),
            patch.object(customer_panel, "list_show_programs_grouped_for_public", return_value=[]),
            patch.object(customer_panel, "ensure_guest_customer", return_value=refusal),
            patch.object(customer_panel, "create_party_order") as create_order,
            patch.object(customer_panel, "_build_site_page", return_value=object()),
            patch.object(customer_panel, "_render_customer_page", return_value=Response("ok")),
        ):
            client = self.app.test_client()
            response = client.post("/party-builder/", data={"program_slug": "ribbon-show"})

        self.assertEqual(response.status_code, 200)
        create_order.assert_not_called()

    def test_verified_auth_returns_to_review_when_builder_draft_exists(self) -> None:
        challenge = {"purpose": "register", "full_name": "Тест", "next_url": "/party-builder/"}
        completed = {"success": True, "customer": {"id": 7, "full_name": "Тест"}}

        with self.app.test_request_context("/auth/telegram-code/"):
            session[customer_panel.PARTY_DRAFT_SESSION_KEY] = {"gift_choices": {"default": "balloons"}}
            with (
                patch.object(customer_panel, "_load_challenge", return_value=challenge),
                patch.object(customer_panel, "_check_gateway_code", return_value={"success": True, "verified": True}),
                patch.object(customer_panel, "complete_customer_phone_auth", return_value=completed),
                patch.object(customer_panel, "_update_challenge"),
            ):
                result = customer_panel._verify_telegram_auth("+998901234567", "request-id", "123456")
            stored_customer_id = session.get(CUSTOMER_SESSION_KEY)

        self.assertTrue(result["success"])
        self.assertEqual(result["redirect_url"], "/party-builder/?resume=review")
        self.assertEqual(stored_customer_id, 7)

    def test_restored_draft_opens_the_review_step(self) -> None:
        customer = {"id": 7, "full_name": "Тест"}
        rendered_page = object()
        with self.app.test_client() as client:
            with client.session_transaction() as current_session:
                current_session[CUSTOMER_SESSION_KEY] = 7
                current_session[customer_panel.PARTY_DRAFT_SESSION_KEY] = {
                    "program_slug": "ribbon-show",
                    "gift_choices": {"default": "balloons"},
                }
            with (
                patch.object(customer_panel, "get_customer_by_id", return_value=customer),
                patch.object(customer_panel, "list_show_programs_for_public", return_value=[]),
                patch.object(customer_panel, "list_show_programs_grouped_for_public", return_value=[]),
                patch.object(customer_panel, "list_character_groups_for_builder", return_value=[]),
                patch.object(customer_panel, "get_show_program_character_slug_map", return_value={}),
                patch.object(customer_panel, "_filtered_busy_dates", return_value={"by_date": {}}),
                patch.object(customer_panel, "_build_site_page", return_value=rendered_page) as build_page,
                patch.object(customer_panel, "_render_customer_page", return_value=Response("ok", 200)),
            ):
                response = client.get("/party-builder/?resume=review")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(build_page.call_args.kwargs["draft_restored"])
        self.assertEqual(build_page.call_args.kwargs["resume_step"], 6)
        self.assertEqual(build_page.call_args.kwargs["form_data"]["gift_choices"], {"default": "balloons"})

    def test_demo_availability_preview_requires_the_admin_session(self) -> None:
        rendered_page = object()
        with self.app.test_client() as client:
            with (
                patch.object(customer_panel, "list_show_programs_for_public", return_value=[]),
                patch.object(customer_panel, "list_show_programs_grouped_for_public", return_value=[]),
                patch.object(customer_panel, "list_character_groups_for_builder", return_value=[]),
                patch.object(customer_panel, "get_show_program_character_slug_map", return_value={}),
                patch.object(customer_panel, "_filtered_busy_dates", return_value={"by_date": {}}),
                patch.object(customer_panel, "_build_site_page", return_value=rendered_page) as build_page,
                patch.object(customer_panel, "_render_customer_page", return_value=Response("ok", 200)),
            ):
                public_response = client.get("/party-builder/?program=ribbon-show&preview=availability")
                public_preview = build_page.call_args.kwargs["availability_preview"]

                with client.session_transaction() as current_session:
                    current_session["admin_user_id"] = 3
                admin_response = client.get("/party-builder/?program=ribbon-show&preview=availability")
                admin_preview = build_page.call_args.kwargs["availability_preview"]

        self.assertEqual(public_response.status_code, 200)
        self.assertFalse(public_preview)
        self.assertEqual(admin_response.status_code, 200)
        self.assertTrue(admin_preview)

    def test_accepted_screen_is_owner_scoped_and_uses_separate_template(self) -> None:
        customer = {"id": 7, "full_name": "Тест"}
        order = {"public_id": "SRP-00007"}
        rendered_page = object()
        with self.app.test_client() as client:
            with client.session_transaction() as current_session:
                current_session[CUSTOMER_SESSION_KEY] = 7
            with (
                patch.object(customer_panel, "get_customer_by_id", return_value=customer),
                patch.object(customer_panel, "get_order_by_public_id", return_value=order) as get_order,
                patch.object(customer_panel, "_build_site_page", return_value=rendered_page) as build_page,
                patch.object(customer_panel, "_render_customer_page", return_value=Response("ok", 200)),
            ):
                response = client.get("/account/orders/SRP-00007/accepted/")

        self.assertEqual(response.status_code, 200)
        get_order.assert_called_once_with("SRP-00007", customer_id=7)
        self.assertEqual(build_page.call_args.kwargs["template_name"], "site/order_accepted_content.html")
        self.assertEqual(build_page.call_args.kwargs["extra_body_class"], "v2-order-accepted-page")

    def test_authenticated_submission_redirects_to_separate_accepted_screen(self) -> None:
        customer = {"id": 7, "full_name": "Тест"}
        created = {"success": True, "order": {"public_id": "SRP-00008"}}
        with self.app.test_client() as client:
            with client.session_transaction() as current_session:
                current_session[CUSTOMER_SESSION_KEY] = 7
            with (
                patch.object(customer_panel, "get_customer_by_id", return_value=customer),
                patch.object(customer_panel, "list_show_programs_for_public", return_value=[]),
                patch.object(customer_panel, "list_show_programs_grouped_for_public", return_value=[]),
                patch.object(customer_panel, "create_party_order", return_value=created) as create_order,
            ):
                response = client.post("/party-builder/", data={"program_slug": "ribbon-show"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/account/orders/SRP-00008/accepted/")
        create_order.assert_called_once()


if __name__ == "__main__":
    unittest.main()
