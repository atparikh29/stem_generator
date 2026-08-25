import Link from "next/link";

export default function Home() {
  return (
    <main className="animate__animated animate__fadeIn">
      <div className="tags" style={{ marginTop: 8 }}>
        <span className="tag tag-accent">Precalculus</span>
        <span className="tag tag-accent">Calculus</span>
        <span className="tag tag-accent">AP Physics 1</span>
      </div>
      <h1 style={{ fontSize: "2.25rem" }}>Practice problems that are provably right.</h1>
      <p className="lede" style={{ fontSize: "1.0625rem" }}>
        Every problem is re-derived by SymPy and physics templates before you
        ever see it.
      </p>
      <p style={{ marginTop: 22 }}>
        <Link href="/practice" style={{ textDecoration: "none" }}>
          <button className="btn-primary">Start practicing →</button>
        </Link>
      </p>
    </main>
  );
}
