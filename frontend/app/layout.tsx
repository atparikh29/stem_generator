import type { ReactNode } from "react";

export const metadata = {
  title: "STEM Problem Generator",
  description: "Neuro-symbolic verified STEM practice",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          maxWidth: 760,
          margin: "0 auto",
          padding: "2rem 1rem",
          lineHeight: 1.5,
        }}
      >
        {children}
      </body>
    </html>
  );
}
