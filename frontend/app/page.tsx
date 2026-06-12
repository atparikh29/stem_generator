import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>Regenerate-Until-Valid</h1>
      <p>
        A neuro-symbolic agentic tutor that generates <strong>verified</strong>{" "}
        Precalculus, single-variable Calculus, and AP Physics 1 problems. Every
        problem is checked with SymPy and physics templates before you ever see
        it.
      </p>
      <p>
        <Link href="/practice">Start practicing →</Link>
      </p>
    </main>
  );
}
