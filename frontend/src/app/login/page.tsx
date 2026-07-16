"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import DisclaimerBanner from "@/components/DisclaimerBanner";
import { apiErrorDetail, login } from "@/lib/api";
import { setSession } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const doLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await login(email.trim(), password);
      setSession({
        token: result.access_token,
        role: result.role,
        fullName: result.full_name,
      });
      router.replace("/");
    } catch (err) {
      setError(apiErrorDetail(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={doLogin} className="flex w-96 flex-col items-center gap-4">
        <span aria-hidden className="text-6xl">🩺</span>
        <h1 className="text-center text-xl font-bold">
          MedAssist — Medical Knowledge Assistant
        </h1>
        <DisclaimerBanner />
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-gray-300 p-2 focus:border-blue-600 focus:outline-none"
        />
        <div className="relative w-full">
          <input
            type={showPassword ? "text" : "password"}
            required
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-gray-300 p-2 pr-10 focus:border-blue-600 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute inset-y-0 right-2 text-sm text-gray-500"
            aria-label="Toggle password visibility"
          >
            {showPassword ? "🙈" : "👁"}
          </button>
        </div>
        {error && <p className="w-full text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-blue-700 p-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
