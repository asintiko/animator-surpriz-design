import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Surpriz — детские праздники в Ташкенте",
    short_name: "Surpriz",
    description: "Шоу-программы и персонажи для детских праздников.",
    start_url: "/",
    display: "standalone",
    background_color: "#FCFAF8",
    theme_color: "#6C1BE3",
    lang: "ru",
    icons: [{ src: "/brand/logo.png", sizes: "512x512", type: "image/png" }],
  };
}
