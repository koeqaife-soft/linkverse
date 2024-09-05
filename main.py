import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore


def recommend_posts(user_id, df, num_recommendations=5):
    user_content_matrix = df.pivot_table(
        index='user_id',
        columns='content_id',
        values='rating'
    ).fillna(0)

    user_similarity = cosine_similarity(user_content_matrix)

    user_similarity_df = pd.DataFrame(
        user_similarity,
        index=user_content_matrix.index,
        columns=user_content_matrix.index
    )

    similar_users = user_similarity_df[user_id].sort_values(ascending=False)

    recommendations = pd.Series(dtype=float)

    for similar_user_id in similar_users.index[1:]:
        similar_user_ratings = user_content_matrix.loc[similar_user_id]

        recommendations = recommendations.add(
            similar_user_ratings * similar_users[similar_user_id],
            fill_value=0
        )

    user_rated_posts = user_content_matrix.loc[user_id]
    recommendations = recommendations.drop(
        user_rated_posts[user_rated_posts > 0].index,
        errors='ignore'
    )

    return (
        recommendations.sort_values(ascending=False)
        .head(num_recommendations).index.tolist()
    )


data = {
    'user_id': [1, 1, 2, 2, 3, 3],
    'content_id': [101, 102, 101, 103, 102, 104],
    'rating': [5, 3, 4, 2, 5, 1]
}

df = pd.DataFrame(data)

recommended_posts = recommend_posts(user_id=3, df=df, num_recommendations=2)
print(f"Рекомендованные посты для пользователя 1: {recommended_posts}")
