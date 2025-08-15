import streamlit as st
import pydeck as pdk
import pandas as pd
# import mysql.connector
import requests
from streamlit_lottie import st_lottie
import json
import plotly.express as px

st.markdown("""
    <style>
    /* Main page background */
    [data-testid="stAppViewContainer"] {
        background-color: #F4F7FB;
        color: #1E1E1E;
    }

    /* Sidebar background */
    [data-testid="stSidebar"] {
        background-color: #E8EEF5;
        color: #1E1E1E;
    }

    /* Transparent header */
    [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0);
    }

    /* Force text color */
    html, body, [class*="css"]  {
        color: #1E1E1E !important;
    }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="PhonePe Transaction Insights", layout="wide")
st.markdown("<h1 style='color:#40E0D0;'>PhonePe Transaction Insights", unsafe_allow_html=True)

# MYSQL CONNECTION 
from sqlalchemy import create_engine
import pymysql

@st.cache_resource
def get_connection():
    engine = create_engine("mysql+pymysql://root:Pasupathi%401710@127.0.0.1/phonepe")
    return engine

engine = get_connection()


# GET STATES 
@st.cache_data
def get_states():
    q = "SELECT DISTINCT States FROM aggregated_transaction ORDER BY States"
    df = pd.read_sql(q, engine)
    return ["All India"] + sorted(df["States"].unique().tolist())

states_list = get_states()

# TABS 
tab1, tab2 = st.tabs([" Home", " Business Case Study"])

#  HOME TAB 
with tab1:
    st.markdown("### Dashboard Filters")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        data_type = st.selectbox(" Data Type", ["Transactions", "Users"])

    with col2:
        year = st.selectbox(" Year", list(range(2018, 2025)))

    with col3:
        quarter = st.selectbox(" Quarter", [1, 2, 3, 4])

    with col4:
        selected_region = st.selectbox("Region", states_list)

    # GEOJSON INDIA MAP
    @st.cache_data
    def load_geojson():
        url = "https://gist.githubusercontent.com/jbrobst/56c13bbbf9d97d187fea01ca62ea5112/raw/e388c4cae20aa53cb5090210a42ebb9b765c0a36/india_states.geojson"
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None

    geojson = load_geojson()

    

    # DATA FETCH
    @st.cache_data
    def get_transaction_summary(year, quarter):
        q = """SELECT Transaction_type, SUM(Transaction_count) AS Count, SUM(Transaction_amount) AS Amount
               FROM aggregated_transaction
               WHERE Years = %s AND Quarter = %s
               GROUP BY Transaction_type"""
        return pd.read_sql(q, engine, params=(year, quarter))

    @st.cache_data
    def get_top_districts(year, quarter):
        q = """SELECT District, SUM(Transaction_amount) AS Amount
               FROM map_transaction
               WHERE Years = %s AND Quarter = %s
               GROUP BY District
               ORDER BY Amount DESC
               LIMIT 10"""
        return pd.read_sql(q, engine, params=(year, quarter))

    @st.cache_data
    def get_top_districts_by_state(year, quarter, state):
        q = """SELECT District, SUM(Transaction_amount) AS Amount
               FROM map_transaction
               WHERE Years = %s AND Quarter = %s AND States = %s
               GROUP BY District
               ORDER BY Amount DESC
               LIMIT 10"""
        return pd.read_sql(q, engine, params=(year, quarter, state))

    @st.cache_data
    def get_map_data(year, quarter):
        q = """SELECT States, SUM(Transaction_amount) AS Total
               FROM aggregated_transaction
               WHERE Years = %s AND Quarter = %s
               GROUP BY States"""
        df = pd.read_sql(q, engine, params=(year, quarter))
        return dict(zip(df["States"], df["Total"])), df

    @st.cache_data
    def get_statewise_transaction_categories(year, quarter):
        query = """
            SELECT States, Transaction_type, SUM(Transaction_amount) AS Amount
            FROM aggregated_transaction
            WHERE Years = %s AND Quarter = %s
            GROUP BY States, Transaction_type
        """
        df = pd.read_sql(query, engine, params=(year, quarter))
        return df.pivot(index="States", columns="Transaction_type", values="Amount").fillna(0)

    @st.cache_data
    def get_user_totals(year, quarter):
        q = """SELECT States, SUM(RegisteredUser) AS Registered, SUM(AppOpens) AS Opens
               FROM map_user
               WHERE Years = %s AND Quarter = %s
               GROUP BY States"""
        return pd.read_sql(q, engine, params=(year, quarter))
        
    # DATA INSERT IN MAP 
    if data_type == "Transactions":
        state_values, _ = get_map_data(year, quarter)
        category_df = get_statewise_transaction_categories(year, quarter)
        tooltip_label = "Total Transactions (₹)"
    else:
        state_values = {}
        category_df = pd.DataFrame()
        tooltip_label = "Total Users"

    max_val = max(state_values.values()) if state_values and max(state_values.values()) > 0 else 1
    user_df = get_user_totals(year, quarter) if data_type == "Users" else None

    for f in geojson["features"]:
        state = f["properties"]["ST_NM"]
        val = state_values.get(state, 0)
        elevation = (val / max_val) * 100
        f["properties"]["elevation"] = elevation
        if data_type == "Transactions" and state in category_df.index:
            cat_data = category_df.loc[state]
            tooltip_text = f"{state}\nTotal: ₹{val:,.0f}"
            for cat, amt in cat_data.items():
                tooltip_text += f"\n{cat}: ₹{amt:,.0f}"
        elif data_type == "Users":
            state_data = user_df[user_df["States"] == state]
            if not state_data.empty:
                reg = int(state_data["Registered"].values[0])
                opens = int(state_data["Opens"].values[0])
                tooltip_text = f"{state}\nRegistered Users: {reg:,}\nApp Opens: {opens:,}"
            else:
                tooltip_text = f"{state}\nNo user data available"
        else:
            tooltip_text = f"{state}\n{tooltip_label}: ₹{val:,.0f}"
        f["properties"]["tooltip"] = tooltip_text

    # STRUCTURING
    col1, col2 = st.columns([2, 2])

    with col1:
        st.markdown("#### Map ")
        view_state = pdk.ViewState(longitude=78.9629, latitude=22.5937, zoom=4, pitch=40)
        layer = pdk.Layer(
            "GeoJsonLayer",
            data=geojson,
            pickable=True,
            extruded=True,
            filled=True,
            get_elevation="properties.elevation",
            elevation_scale=1.5,
            get_fill_color="[255 - properties.elevation * 2, 100, 200, 180]",
            auto_highlight=True,
        )
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"text": "{tooltip}"}))

    with col2:
        st.markdown("#### Transactions" if data_type == "Transactions" else "####  User Insights")

        if data_type == "Transactions":
            st.markdown("##### Transaction Summary")
            full_txn_df = get_transaction_summary(year, quarter)
            total_txn_count = full_txn_df["Count"].sum()
            total_txn_amount = full_txn_df["Amount"].sum()
            if selected_region == "All India":
                st.metric(" Total Transactions", f"{int(total_txn_count):,}")
                st.metric(" Total Amount", f"₹{int(total_txn_amount):,}")
            else:
                query = """SELECT SUM(Transaction_count) AS Count, SUM(Transaction_amount) AS Amount
                           FROM aggregated_transaction
                           WHERE Years = %s AND Quarter = %s AND States = %s"""
                state_df = pd.read_sql(query, engine, params=(year, quarter, selected_region))
                state_count = int(state_df["Count"].iloc[0]) if not state_df.empty else 0
                state_amount = state_df["Amount"].iloc[0] if not state_df.empty else 0
                st.metric(f" Total Transactions in {selected_region}", f"{int(state_count):,}")
                st.metric(f" Total Amount in {selected_region}", f"₹{int(state_amount):,}")

            st.markdown("---")
            col_districts, col_states, col_pins = st.columns(3)

            with col_districts:
                st.markdown("##### Top 10 Districts")
                if selected_region == "All India":
                    top_districts_df = get_top_districts(year, quarter)
                else:
                    top_districts_df = get_top_districts_by_state(year, quarter, selected_region)
                top_districts_df["Amount"] = top_districts_df["Amount"].apply(lambda x: f"₹{x:,.0f}")
                for idx, row in top_districts_df.iterrows():
                    st.markdown(f"- **{row['District']}** : {row['Amount']}")

            with col_states:
                st.markdown("#####  Top 10 States")
                _, state_df = get_map_data(year, quarter)
                top_states_df = state_df.sort_values("Total", ascending=False).head(10)
                top_states_df["Total"] = top_states_df["Total"].apply(lambda x: f"₹{x:,.0f}")
                for idx, row in top_states_df.iterrows():
                    st.markdown(f"- **{row['States']}** : {row['Total']}")


        elif data_type == "Users":
            st.markdown("##### Total Registered Users & App Opens")
            df_users = get_user_totals(year, quarter)
            total_registered = df_users["Registered"].sum()
            total_opens = df_users["Opens"].sum()
            st.subheader(" All India Summary")
            st.metric(" Registered Users", f"{int(total_registered):,}")
            st.metric(" App Opens", f"{int(total_opens):,}")
            if selected_region != "All India":
                state_df = df_users[df_users["States"] == selected_region]
                if not state_df.empty:
                    state_reg = int(state_df["Registered"].values[0])
                    state_open = int(state_df["Opens"].values[0])
                    st.subheader(f" {selected_region} Summary")
                    st.metric(" Registered Users", f"{state_reg:,}")
                    st.metric(" App Opens", f"{state_open:,}")
                else:
                    st.warning("No user data available for the selected region.")
            st.markdown("######  Top 10 States by Total Users")
            df_users["Total"] = df_users["Registered"] + df_users["Opens"]
            df_top_states = df_users.sort_values("Total", ascending=False).head(10)
            for idx, row in df_top_states.iterrows():
                st.markdown(f"- **{row['States']}** : {int(row['Total']):,} users")


# BUSINESS CASE STUDY 

with tab2:
    st.markdown("## BUSINESS CASE STUDY")

    question_list = [
        "1. Decoding Transaction Dynamics on PhonePe",
        "2. Device Dominance and User Engagement Analysis",
        "3. Insurance Penetration and Growth Potential Analysis",
        "4. Transaction Analysis for Market Expansion",
        "5. User Engagement and Growth Strategy"
    ]
    selected_question = st.selectbox("Select a Case Study", question_list, key="business_case_study_selector")

    # CASE STUDY 1: Decoding Transaction Dynamics on PhonePe
    def show_case_study_1():
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_year = st.selectbox(" Year", list(range(2018, 2025)), key="cs1_year")
        with col2:
            selected_quarter = st.selectbox(" Quarter", [1, 2, 3, 4], key="cs1_quarter")
        with col3:
            selected_state = st.selectbox(" State", states_list, key="cs1_state")

        # Choropleth Map
        map_query = """
            SELECT States, SUM(Transaction_amount) AS TotalAmount
            FROM aggregated_transaction
            WHERE Years = %s AND Quarter = %s
            GROUP BY States
        """
        map_df = pd.read_sql(map_query, engine, params=(selected_year, selected_quarter))

        fig_map = px.choropleth(
            map_df,
            geojson=geojson,
            featureidkey="properties.ST_NM",
            locations="States",
            color="TotalAmount",
            color_continuous_scale="Turbo",
            title=f"Total Transaction Amount by State (Q{selected_quarter}, {selected_year})"
        )
        fig_map.update_geos(fitbounds="locations", visible=False)
        st.plotly_chart(fig_map, use_container_width=True)

        # Payment Method Popularity Pie Charts
        st.markdown("###  Payment Method Popularity")
        if selected_state == "All India":
            pie_query = """
                SELECT Transaction_type, SUM(Transaction_count) AS TotalCount, SUM(Transaction_amount) AS TotalAmount
                FROM aggregated_transaction
                WHERE Years = %s AND Quarter = %s
                GROUP BY Transaction_type
            """
            pie_df = pd.read_sql(pie_query, engine, params=(selected_year, selected_quarter))
        else:
            pie_query = """
                SELECT Transaction_type, SUM(Transaction_count) AS TotalCount, SUM(Transaction_amount) AS TotalAmount
                FROM aggregated_transaction
                WHERE Years = %s AND Quarter = %s AND States = %s
                GROUP BY Transaction_type
            """
            pie_df = pd.read_sql(pie_query, engine, params=(selected_year, selected_quarter, selected_state))

        col1, col2 = st.columns(2)
        with col1:
            fig_pie1 = px.pie(pie_df, names="Transaction_type", values="TotalCount",
                              title="Transaction Count by Payment Method")
            st.plotly_chart(fig_pie1, use_container_width=True)
        with col2:
            fig_pie2 = px.pie(pie_df, names="Transaction_type", values="TotalAmount",
                              title="Transaction Amount by Payment Method")
            st.plotly_chart(fig_pie2, use_container_width=True)

        # Top  States
        st.markdown("###  Top  States by Transaction Amount")
        if selected_state == "All India":
            top_states_df = map_df.sort_values("TotalAmount", ascending=False).head(10)
        else:
            top_states_df = map_df[map_df["States"] == selected_state]

        fig_bar = px.bar(top_states_df, x="States", y="TotalAmount", color="States",
                         text_auto=".2s", title="Top Transaction States")
        st.plotly_chart(fig_bar, use_container_width=True)

        # Category Breakdown Line Chart
        st.markdown("###  Transaction Category Breakdown by State")
        if selected_state == "All India":
            breakdown_query = """
                SELECT States, Transaction_type, SUM(Transaction_amount) AS Amount
                FROM aggregated_transaction
                WHERE Years = %s AND Quarter = %s
                GROUP BY States, Transaction_type
            """
            breakdown_df = pd.read_sql(breakdown_query, engine, params=(selected_year, selected_quarter))
        else:
            breakdown_query = """
                SELECT States, Transaction_type, SUM(Transaction_amount) AS Amount
                FROM aggregated_transaction
                WHERE Years = %s AND Quarter = %s AND States = %s
                GROUP BY States, Transaction_type
            """
            breakdown_df = pd.read_sql(breakdown_query, engine, params=(selected_year, selected_quarter, selected_state))

        if not breakdown_df.empty:
            fig_line = px.line(
                breakdown_df,
                x="Transaction_type",
                y="Amount",
                color="States",
                markers=True,
                title="Transaction by Payment Category and State"
            )
            fig_line.update_layout(xaxis_title="Payment Category", yaxis_title="Transaction Amount (₹)", xaxis_tickangle=-30)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.warning("No transaction data found for the selected filters.")

        # Trend Analysis
        st.markdown("### Trend Analysis")
        if selected_state == "All India":
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel,
                       SUM(Transaction_amount) AS TotalAmount
                FROM aggregated_transaction
                GROUP BY Years, Quarter
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine)
        else:
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel,
                       SUM(Transaction_amount) AS TotalAmount
                FROM aggregated_transaction
                WHERE States = %s
                GROUP BY Years, Quarter
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine, params=(selected_state,))

        if not trend_df.empty:
            fig_trend = px.bar(
                trend_df,
                x="QuarterLabel",
                y="TotalAmount",
                text_auto=".2s",
                color="QuarterLabel",
                title=f"Transaction Amount Trend per Quarter - {selected_state}"
            )
            fig_trend.update_layout(xaxis_title="Quarter", yaxis_title="Transaction Amount (₹)", xaxis_tickangle=-45, showlegend=False)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.warning("No transaction trend data available for the selected region.")

    # CASE STUDY 2
    def show_case_study_2():
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_year = st.selectbox(" Year", list(range(2018, 2025)), key="cs2_year")
        with col2:
            selected_quarter = st.selectbox(" Quarter", [1, 2, 3, 4], key="cs2_quarter")
        with col3:
            selected_state = st.selectbox(" State", states_list, key="cs2_state")

        # Top Device Brands
        st.markdown("### Top  Device Brands by User Count")
        if selected_state == "All India":
            brand_query = """
                SELECT Brands, SUM(Transaction_count) AS TotalCount
                FROM aggregated_user
                WHERE Years = %s AND Quarter = %s
                GROUP BY Brands
                ORDER BY TotalCount DESC
                LIMIT 15
            """
            params = (selected_year, selected_quarter)
        else:
            brand_query = """
                SELECT Brands, SUM(Transaction_count) AS TotalCount
                FROM aggregated_user
                WHERE Years = %s AND Quarter = %s AND States = %s
                GROUP BY Brands
                ORDER BY TotalCount DESC
                LIMIT 15
            """
            params = (selected_year, selected_quarter, selected_state)

        brand_df = pd.read_sql(brand_query, engine, params=params)
        if not brand_df.empty:
            fig_bar = px.bar(
                brand_df,
                x="Brands",
                y="TotalCount",
                color="Brands",
                text_auto=".2s",
                title=f"Top  Brands - Q{selected_quarter} {selected_year} ({selected_state})"
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("No brand data available for selected filters.")

        # App Opens vs Registered Users
        st.markdown("### App Opens vs Registered Users")
        if selected_state == "All India":
            user_query = """
                SELECT States, SUM(RegisteredUser) AS Registered, SUM(AppOpens) AS Opens
                FROM map_user
                WHERE Years = %s AND Quarter = %s
                GROUP BY States
            """
            user_params = (selected_year, selected_quarter)
        else:
            user_query = """
                SELECT States, SUM(RegisteredUser) AS Registered, SUM(AppOpens) AS Opens
                FROM map_user
                WHERE Years = %s AND Quarter = %s AND States = %s
                GROUP BY States
            """
            user_params = (selected_year, selected_quarter, selected_state)

        user_df = pd.read_sql(user_query, engine, params=user_params)
        if not user_df.empty:
            fig_scatter = px.scatter(
                user_df,
                x="Registered",
                y="Opens",
                size="Registered",
                color="States",
                hover_name="States",
                title="User Engagement: App Opens vs Registered Users",
                labels={"Registered": "Registered Users", "Opens": "App Opens"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("No user data available for selected filters.")

        # Brand Share Pie Chart
        st.markdown("###  Device Brand Market Share")
        if selected_state == "All India":
            pie_query = """
                SELECT Brands, SUM(Transaction_count) AS TotalCount
                FROM aggregated_user
                WHERE Years = %s AND Quarter = %s
                GROUP BY Brands
            """
            pie_params = (selected_year, selected_quarter)
        else:
            pie_query = """
                SELECT Brands, SUM(Transaction_count) AS TotalCount
                FROM aggregated_user
                WHERE Years = %s AND Quarter = %s AND States = %s
                GROUP BY Brands
            """
            pie_params = (selected_year, selected_quarter, selected_state)

        pie_df = pd.read_sql(pie_query, engine, params=pie_params)
        if not pie_df.empty:
            fig_pie = px.pie(
                pie_df,
                names="Brands",
                values="TotalCount",
                title="Device Brand Market Share",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("No brand share data available for selected filters.")

        # Trend Line of Brand Usage
        st.markdown("###  Brand Usage Trend Over Quarters")
        if selected_state == "All India":
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel, Brands, SUM(Transaction_count) AS Count
                FROM aggregated_user
                GROUP BY Years, Quarter, Brands
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine)
        else:
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel, Brands, SUM(Transaction_count) AS Count
                FROM aggregated_user
                WHERE States = %s
                GROUP BY Years, Quarter, Brands
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine, params=(selected_state,))

        if not trend_df.empty:
            fig_trend = px.line(
                trend_df,
                x="QuarterLabel",
                y="Count",
                color="Brands",
                markers=True,
                title=f"Quarterly Device Usage Trend - {selected_state}"
            )
            fig_trend.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.warning("No brand trend data available.")
    # CASE STUDY 3
    def show_case_study_3():
        # Unique keys to prevent widget conflicts
        col1, col2, col3 = st.columns(3)
        with col1:
            cs3_year = st.selectbox(" Year", list(range(2018, 2025)), key="cs3_year_unique")
        with col2:
            cs3_quarter = st.selectbox(" Quarter", [1, 2, 3, 4], key="cs3_quarter_unique")
        with col3:
            cs3_state = st.selectbox(" State", states_list, key="cs3_state_unique")

        # Insurance Transactions Choropleth Map
        map_query = """
            SELECT States AS State, SUM(Transaction_count) AS TransactionCount, SUM(Transaction_amount) AS TotalAmount 
            FROM map_insurance 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States
        """
        map_df = pd.read_sql(map_query, engine, params=(cs3_year, cs3_quarter))
        st.markdown("### Insurance Transactions Across States")
        fig_map = px.choropleth(
            map_df,
            geojson=geojson,
            featureidkey='properties.ST_NM',
            locations='State',
            color='TransactionCount',
            color_continuous_scale='blues',
            title='Insurance Transactions by State'
        )
        fig_map.update_geos(fitbounds="locations", visible=False)
        st.plotly_chart(fig_map, use_container_width=True)

        # Top States by Insurance
        top_query = """
            SELECT States AS State, SUM(Transaction_count) AS TransactionCount 
            FROM top_insurance 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States 
            ORDER BY TransactionCount DESC 
            LIMIT 15
        """
        top_df = pd.read_sql(top_query, engine, params=(cs3_year, cs3_quarter))
        st.markdown("###  Top 10 States by Insurance Adoption")
        fig_bar = px.bar(
            top_df,
            x='TransactionCount',
            y='State',
            orientation='h',
            color='TransactionCount',
            title='Top  States by Insurance Transactions'
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Quarterly Insurance Trend
        trend_query = """
            SELECT Quarter, SUM(Insurance_count) AS TransactionCount 
            FROM aggregated_insurance 
            WHERE Years = %s 
            GROUP BY Quarter
            ORDER BY Quarter
        """
        trend_df = pd.read_sql(trend_query, engine, params=(cs3_year,))
        st.markdown("###  Quarterly Insurance Transaction Trend")
        fig_line = px.line(
            trend_df,
            x='Quarter',
            y='TransactionCount',
            markers=True,
            title=f'Quarterly Insurance Trends - {cs3_year}'
        )
        st.plotly_chart(fig_line, use_container_width=True)

        # Bubble Plot: Insurance vs Registered Users
        user_query = """
            SELECT States AS State, SUM(RegisteredUser) AS RegisteredUsers 
            FROM map_user 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States
        """
        insurance_query = """
            SELECT States AS State, SUM(Transaction_count) AS InsuranceTransactions 
            FROM map_insurance 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States
        """
        user_df = pd.read_sql(user_query, engine, params=(cs3_year, cs3_quarter))
        insurance_df = pd.read_sql(insurance_query, engine, params=(cs3_year, cs3_quarter))
        merged_df = pd.merge(user_df, insurance_df, on='State', how='inner')

        st.markdown("###  Insurance vs User Penetration Ratio")
        fig_bubble = px.scatter(
            merged_df,
            x='RegisteredUsers',
            y='InsuranceTransactions',
            size='InsuranceTransactions',
            color='State',
            title='Insurance Transactions vs Registered Users by State',
            labels={
                'RegisteredUsers': 'Registered Users',
                'InsuranceTransactions': 'Insurance Transactions'
            }
        )
        st.plotly_chart(fig_bubble, use_container_width=True)

    # CASE STUDY 4
    def show_case_study_4():
        col1, col2, col3 = st.columns(3)
        with col1:
            cs4_year = st.selectbox(" Year", list(range(2018, 2025)), key="cs4_year_unique")
        with col2:
            cs4_quarter = st.selectbox(" Quarter", [1, 2, 3, 4], key="cs4_quarter_unique")
        with col3:
            cs4_state = st.selectbox(" State", states_list, key="cs4_state_unique")

        # --- Choropleth Map ---
        map_query = """
            SELECT States AS State, SUM(Transaction_amount) AS TotalAmount 
            FROM map_transaction 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States
        """
        map_df = pd.read_sql(map_query, engine, params=(cs4_year, cs4_quarter))
        map_df["TotalAmount"] = map_df["TotalAmount"].astype(float)
        st.markdown("###  Market Coverage by State (Transaction Amount)")
        fig_map = px.choropleth(
            map_df,
            geojson=geojson,
            featureidkey='properties.ST_NM',
            locations='State',
            color='TotalAmount',
            color_continuous_scale='Viridis',
            title='Total Transaction Amounts by State'
        )
        fig_map.update_geos(fitbounds="locations", visible=False)
        st.plotly_chart(fig_map, use_container_width=True)

        # --- Pan-India Quarterly Growth Trend ---
        trend_query = """
            SELECT Years, Quarter, SUM(Transaction_amount) AS TotalAmount 
            FROM aggregated_transaction 
            GROUP BY Years, Quarter 
            ORDER BY Years, Quarter
        """
        trend_df = pd.read_sql(trend_query, engine)
        trend_df["TotalAmount"] = trend_df["TotalAmount"].astype(float)
        trend_df["Quarter"] = trend_df["Quarter"].astype(str)
        trend_df["Years"] = trend_df["Years"].astype(str)
        trend_df['Period'] = trend_df['Years'] + "-Q" + trend_df['Quarter']
        st.markdown("### Quarterly Transaction Growth Trend (India)")
        fig_line = px.line(
            trend_df,
            x="Period",
            y="TotalAmount",
            markers=True,
            title="Pan-India Transaction Growth Over Time"
        )
        st.plotly_chart(fig_line, use_container_width=True)

        # --- Bubble Plot: Volume vs Count ---
        bubble_query = """
            SELECT States AS State, SUM(Transaction_amount) AS TotalAmount, SUM(Transaction_count) AS TransactionCount 
            FROM map_transaction 
            WHERE Years = %s AND Quarter = %s 
            GROUP BY States
        """
        bubble_df = pd.read_sql(bubble_query, engine, params=(cs4_year, cs4_quarter))
        bubble_df["TotalAmount"] = bubble_df["TotalAmount"].astype(float)
        bubble_df["TransactionCount"] = bubble_df["TransactionCount"].astype(int)
        st.markdown("### Market Size vs Frequency (by State)")
        fig_bubble = px.scatter(
            bubble_df,
            x="TransactionCount",
            y="TotalAmount",
            size="TotalAmount",
            color="State",
            hover_name="State",
            title="Market Expansion Opportunities by State",
            labels={
                "TransactionCount": "Transaction Count",
                "TotalAmount": "Transaction Amount"
            }
        )
        st.plotly_chart(fig_bubble, use_container_width=True)

    # CASE STUDY 5
    def show_case_study_5():

        col1, col2, col3 = st.columns(3)
        with col1:
            cs5_year = st.selectbox(" Year", list(range(2018, 2025)), key="cs5_year")
        with col2:
            cs5_quarter = st.selectbox(" Quarter", [1, 2, 3, 4], key="cs5_quarter")
        with col3:
            cs5_state = st.selectbox(" State", states_list, key="cs5_state")

        # Choropleth Map: Registered Users by State
        st.markdown("###  Registered Users Distribution")
        user_map_query = """
            SELECT States AS State, SUM(RegisteredUser) AS TotalRegistered
            FROM map_user
            WHERE Years = %s AND Quarter = %s
            GROUP BY States
        """
        user_map_df = pd.read_sql(user_map_query, engine, params=(cs5_year, cs5_quarter))
        fig_map = px.choropleth(
            user_map_df,
            geojson=geojson,
            featureidkey='properties.ST_NM',
            locations='State',
            color='TotalRegistered',
            color_continuous_scale='YlGnBu',
            title=f"Registered Users by State (Q{cs5_quarter}, {cs5_year})"
        )
        fig_map.update_geos(fitbounds="locations", visible=False)
        st.plotly_chart(fig_map, use_container_width=True)

        # App Opens Trend Line
        st.markdown("###  App Engagement Trend Over Quarters")
        if cs5_state == "All India":
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel,
                       SUM(AppOpens) AS TotalOpens
                FROM map_user
                GROUP BY Years, Quarter
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine)
        else:
            trend_query = """
                SELECT CONCAT(Years, '-Q', Quarter) AS QuarterLabel,
                       SUM(AppOpens) AS TotalOpens
                FROM map_user
                WHERE States = %s
                GROUP BY Years, Quarter
                ORDER BY Years, Quarter
            """
            trend_df = pd.read_sql(trend_query, engine, params=(cs5_state,))
        fig_line = px.line(
            trend_df,
            x="QuarterLabel",
            y="TotalOpens",
            markers=True,
            title=f"App Opens Over Time - {cs5_state}"
        )
        fig_line.update_layout(xaxis_title="Quarter", yaxis_title="App Opens")
        st.plotly_chart(fig_line, use_container_width=True)

        # Engagement Ratio per State
        st.markdown("###  App Opens to Registered Users Ratio")
        ratio_query = """
            SELECT States AS State, SUM(RegisteredUser) AS Registered, SUM(AppOpens) AS Opens
            FROM map_user
            WHERE Years = %s AND Quarter = %s
            GROUP BY States
        """
        ratio_df = pd.read_sql(ratio_query, engine, params=(cs5_year, cs5_quarter))
        ratio_df["EngagementRatio"] = (ratio_df["Opens"] / ratio_df["Registered"]).round(2)
        fig_bar = px.bar(
            ratio_df.sort_values("EngagementRatio", ascending=False).head(10),
            x="State",
            y="EngagementRatio",
            color="EngagementRatio",
            title="Top States by App Opens per Registered User"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Bubble Plot: Growth Potential
        st.markdown("###  Growth Strategy: Users vs Engagement")
        bubble_df = ratio_df.copy()
        fig_bubble = px.scatter(
            bubble_df,
            x="Registered",
            y="Opens",
            size="EngagementRatio",
            color="State",
            hover_name="State",
            title="User Growth vs Engagement",
            labels={"Registered": "Registered Users", "Opens": "App Opens"}
        )
        st.plotly_chart(fig_bubble, use_container_width=True)


    if selected_question == question_list[0]:
        show_case_study_1()
    elif selected_question == question_list[1]:
        show_case_study_2()
    elif selected_question == question_list[2]:
        show_case_study_3()
    elif selected_question == question_list[3]:
        show_case_study_4()
    elif selected_question == question_list[4]:
        show_case_study_5()


