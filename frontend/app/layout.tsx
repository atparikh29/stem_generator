import type { ReactNode } from "react";
import Link from "next/link";
import "animate.css/animate.min.css";
import "./globals.css";

export const metadata = {
  title: "STEM Problem Generator",
  description: "Neuro-symbolic verified STEM practice",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="appbar">
          <Link href="/" className="brand">
            <span className="brand-mark" aria-hidden="true">
              ∑
            </span>
            Regenerate-Until-Valid
          </Link>
        </header>
        <div className="shell">{children}</div>
      </body>
    </html>
  );
}
