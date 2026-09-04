import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] });
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] });
const siteOrigin = process.env.NEXT_PUBLIC_SITE_ORIGIN ?? 'https://fantasy-football-26.vista-verde-6860.chatgpt.site';

const title = 'Draft Room — Fantasy Football 2026';
const description = 'Live 2026 PPR player rankings grounded in NFL opportunity, team environment, and market timing.';

export const metadata: Metadata = {
  metadataBase: new URL(siteOrigin),
  title,
  description,
  openGraph: {
    title,
    description,
    type: 'website',
    images: [{ url: '/og.png', width: 1730, height: 909, alt: 'Draft Room — Fantasy Football 2026 analytics dashboard' }],
  },
  twitter: {
    card: 'summary_large_image',
    title,
    description,
    images: ['/og.png'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body></html>;
}
