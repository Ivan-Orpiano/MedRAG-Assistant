"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import DisclaimerBanner from "@/components/DisclaimerBanner";
import { clearSession, getSession, type Session } from "@/lib/session";

export default function PageFrame({
  title,
  active,
  children,
}: {
  title: string;
  active: "chat" | "documents" | "admin";
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [session, setSessionState] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const current = getSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    setSessionState(current);
    setReady(true);
  }, [router]);

  if (!ready || !session) return null;

  const links: Array<{ text: string; href: string; key: string }> = [
    { text: "Chat", href: "/", key: "chat" },
    { text: "Documents", href: "/documents", key: "documents" },
  ];
  if (session.role === "admin") links.push({ text: "Admin", href: "/admin", key: "admin" });

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <>
      <header className="flex items-center gap-2 bg-blue-900 px-4 py-3 text-white">
        <span aria-hidden className="text-2xl">🩺</span>
        <span className="mr-6 text-lg font-bold">MedAssist</span>
        {links.map(({ text, href, key }) => (
          <Link
            key={key}
            href={href}
            className={`px-2 text-white ${key === active ? "font-bold underline" : "no-underline"}`}
          >
            {text}
          </Link>
        ))}
        <span className="grow" />
        <span className="mr-2 text-sm">
          {session.fullName} ({session.role})
        </span>
        <button
          onClick={logout}
          className="rounded px-3 py-1 text-sm text-white hover:bg-blue-800"
        >
          Log out
        </button>
      </header>
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4">
        <DisclaimerBanner />
        <h1 className="text-2xl font-bold">{title}</h1>
        {children}
      </main>
    </>
  );
}
