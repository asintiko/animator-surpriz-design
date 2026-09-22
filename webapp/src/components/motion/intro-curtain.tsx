"use client";

import Image from "next/image";
import { useEffect, useRef } from "react";

const SESSION_KEY = "surpriz-intro-seen";

export function IntroCurtain() {
  const curtainRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const hasSeenIntro = window.sessionStorage.getItem(SESSION_KEY) === "1";
    if (hasSeenIntro) {
      if (curtainRef.current) curtainRef.current.hidden = true;
      return;
    }

    window.sessionStorage.setItem(SESSION_KEY, "1");
    const timeout = window.setTimeout(() => {
      if (curtainRef.current) curtainRef.current.hidden = true;
    }, 720);
    return () => window.clearTimeout(timeout);
  }, []);

  return (
    <div className="intro-curtain" aria-hidden="true" ref={curtainRef}>
      <div className="intro-mark">
        <Image src="/brand/logo.png" alt="" width={112} height={112} priority />
        <span>Ваш праздник начинается</span>
      </div>
    </div>
  );
}
