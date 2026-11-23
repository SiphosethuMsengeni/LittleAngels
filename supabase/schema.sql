create table if not exists public.app_data (
    key text primary key,
    value jsonb not null
);

alter table public.app_data enable row level security;
grant all on table public.app_data to service_role;

create table if not exists public.orders (
    id text primary key,
    created_at timestamptz not null,
    data jsonb not null
);

alter table public.orders enable row level security;
grant all on table public.orders to service_role;

create or replace function public.record_order(p_order jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_catalog jsonb;
    updated_catalog jsonb;
    requested_item jsonb;
    available_stock integer;
begin
    select value into current_catalog
    from public.app_data
    where key = 'catalog'
    for update;

    if current_catalog is null then
        return jsonb_build_object('ok', false);
    end if;

    for requested_item in
        select item.value from jsonb_array_elements(p_order -> 'items') as item(value)
    loop
        select (size.value ->> 'stock')::integer into available_stock
        from jsonb_array_elements(current_catalog) as product(value)
        cross join lateral jsonb_array_elements(product.value -> 'sizes') as size(value)
        where product.value ->> 'id' = requested_item ->> 'id'
          and size.value ->> 'name' = requested_item ->> 'size'
        limit 1;

        if available_stock is null
           or available_stock < (requested_item ->> 'quantity')::integer then
            return jsonb_build_object('ok', false);
        end if;

        select jsonb_agg(
            case
                when product.value ->> 'id' = requested_item ->> 'id' then
                    jsonb_set(
                        product.value,
                        '{sizes}',
                        (
                            select jsonb_agg(
                                case
                                    when size.value ->> 'name' = requested_item ->> 'size' then
                                        jsonb_set(
                                            size.value,
                                            '{stock}',
                                            to_jsonb(
                                                (size.value ->> 'stock')::integer
                                                - (requested_item ->> 'quantity')::integer
                                            )
                                        )
                                    else size.value
                                end
                                order by size.ordinality
                            )
                            from jsonb_array_elements(product.value -> 'sizes')
                                with ordinality as size(value, ordinality)
                        )
                    )
                else product.value
            end
            order by product.ordinality
        ) into updated_catalog
        from jsonb_array_elements(current_catalog)
            with ordinality as product(value, ordinality);

        current_catalog := updated_catalog;
    end loop;

    update public.app_data set value = current_catalog where key = 'catalog';

    insert into public.orders (id, created_at, data)
    values (
        p_order ->> 'order_reference',
        (p_order ->> 'created_at')::timestamptz,
        p_order
    );

    return jsonb_build_object('ok', true);
end;
$$;

revoke all on function public.record_order(jsonb) from public;
grant execute on function public.record_order(jsonb) to service_role;

insert into storage.buckets (id, name, public)
values ('little-angels-images', 'little-angels-images', false)
on conflict (id) do nothing;

notify pgrst, 'reload schema';
