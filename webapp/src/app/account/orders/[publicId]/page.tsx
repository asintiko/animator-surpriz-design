import { OrderDetail } from "@/features/account/order-detail";

export default async function OrderPage({ params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  return <section className="page-section"><div className="container"><OrderDetail publicId={publicId} /></div></section>;
}
