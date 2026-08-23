import type { MetadataRoute } from "next";

/**
 * Next serves this at /manifest.webmanifest and links it from every page.
 * A typed manifest rather than a hand-kept JSON file: a wrong `display` or a
 * missing icon size is a build error instead of an iPhone that installs a
 * browser shortcut and calls it an app.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Everyday English",
    short_name: "English",
    description: "Ten minutes a day, in the English people actually speak.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f7f5f0",
    theme_color: "#10201f",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
