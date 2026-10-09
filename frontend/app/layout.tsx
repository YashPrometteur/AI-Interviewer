import React from 'react';

export const metadata = {
  title: 'AI Interviewer',
  description: 'AI-Powered Technical & Behavioral Interview Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
