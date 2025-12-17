import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Icon from "@/components/ui/icon";
import type { Order, SenderData, CarrierData } from "@/types";

interface OrdersListProps {
  orders: Order[];
}

const OrdersList = ({ orders }: OrdersListProps) => {
  if (orders.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Icon name="Inbox" size={48} className="mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">Заявок пока нет</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {orders.map((order) => (
        <Card key={order.id} className="hover-scale">
          <CardHeader>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                  order.type === "sender" ? "bg-blue-100" : "bg-green-100"
                }`}>
                  <Icon 
                    name={order.type === "sender" ? "PackageOpen" : "Truck"} 
                    size={24}
                    className={order.type === "sender" ? "text-blue-600" : "text-green-600"}
                  />
                </div>
                <div>
                  <CardTitle className="text-base">
                    {order.type === "sender" ? "Заявка отправителя" : "Заявка перевозчика"}
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">
                    {new Date(order.createdAt).toLocaleString("ru-RU")}
                  </p>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {order.type === "sender" ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Отправитель:</span>
                  <span className="font-medium">{(order.data as SenderData).senderName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Телефон:</span>
                  <span className="font-medium">{(order.data as SenderData).phone}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Адрес забора:</span>
                  <span className="font-medium text-right">{(order.data as SenderData).pickupAddress}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Склад:</span>
                  <span className="font-medium">{(order.data as SenderData).warehouse}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Груз:</span>
                  <span className="font-medium">
                    {(order.data as SenderData).cargoType === "pallet" ? "Паллеты" : "Короба"} 
                    {(order.data as SenderData).cargoQuantity && ` × ${(order.data as SenderData).cargoQuantity}`}
                  </span>
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Водитель:</span>
                  <span className="font-medium">{(order.data as CarrierData).driverName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Телефон:</span>
                  <span className="font-medium">{(order.data as CarrierData).phone}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Автомобиль:</span>
                  <span className="font-medium">
                    {(order.data as CarrierData).carBrand} {(order.data as CarrierData).carModel}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Гос. номер:</span>
                  <span className="font-medium">{(order.data as CarrierData).licensePlate}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Вместимость:</span>
                  <span className="font-medium">
                    {(order.data as CarrierData).capacityType === "pallet" ? "Паллеты" : "Короба"}
                    {(order.data as CarrierData).capacityQuantity && ` × ${(order.data as CarrierData).capacityQuantity}`}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

export default OrdersList;