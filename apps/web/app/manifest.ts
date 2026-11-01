import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Platon — инвестиционный Copilot",
    short_name: "Platon",
    description:
      "AI-агент для облигационного портфеля: аналитика, риск, купоны и сделки.",
    start_url: "/",
    display: "standalone",
    background_color: "#07110f",
    theme_color: "#07110f",
    orientation: "portrait",
    lang: "ru",
    categories: ["finance", "productivity"],
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      {
        name: "Bond Copilot",
        short_name: "Облигации",
        url: "/?bot=bond",
        icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }],
      },
      {
        name: "Freelance Radar",
        short_name: "Фриланс",
        url: "/?bot=freelance",
        icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }],
      },
    ],
  };
}
