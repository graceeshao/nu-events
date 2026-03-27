import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NU Events — Northwestern Campus Events",
  description:
    "Discover events happening across Northwestern University's campus — academics, social, career, arts, sports, and more.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        {children}
      </body>
    </html>
  );
}
